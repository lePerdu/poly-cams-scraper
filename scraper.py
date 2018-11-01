#!/usr/bin/env python

## scraper.py
# Functions for scraping data from the CAMS portal
#

import re
from datetime import datetime

import requests
from lxml import html


def pairs_to_dict(pairs):
    return {k: v for k, v in pairs if k}


def get_attr(attrs, name):
    for k, v in attrs:
        if k == name: return v
    return None


def get_text(elem):
    return elem.text.strip()


def parse_date(datestr):
    '''
    Parses a date in the format %m/%d/%Y into a POSIX timestamp
    TODO Should this output in ISO format instead?
    '''
    return int(datetime.strptime(datestr, '%m/%d/%Y').timestamp())


def parse_time(timestr):
    '''
    Parses a time in the format %H:%M:%S into a POSIX timestamp (number
    of seconds from the start of the day)
    TODO Should this output in ISO format instead?
    '''

    # strptime uses 1900-01-01 as the default date, so subtract it out to get
    # the timestamp from the start of the day
    return int((datetime.strptime(timestr, '%I:%M:%S %p')
          - datetime(1900, 1, 1)).total_seconds())


def parse_course_id(id):
    '''
    Parses a course identifier of the form:
        DEP<COURSE #>TYPE<SECTION #>
    Into a (department, course, section) tuple

    Note: Some older courses do not have a type field or section
    '''

    # TODO What other suffixes are there besides C (for lab) and how can they
    # be differentiated from the type of course (i.e. GENMAT, ENGR)?
    dep, number, type, sec = \
        re.match(r'(\w{3})(\w{4}C?)([^\d]+)?(\d+)?', id).groups()
    # Some course identifiers don't include the section, so we assume it's 1
    return {
        'department': dep,
        'number': number,
        'type': type,
        'section': sec and int(sec) or 1,
    }


def parse_sections(tree):
    '''
    The formatting of this table is total crap and a real pain ass to parse,
    but here is the general format (the parts used to scrape out the info we
    ):
        <table>
            <thead>...</thead>

            <!-- Each course consists of 3 rows: -->

            <tr class="courseInfo">
                <td>{course identifier}<div>{book list button}</div></td>
                <td>{title}</td>
                <td>{number of credits}</td>
                <td>{start date}</td>
                <td>{end date}</td>
                <td>{max entries}</td>
                <td>{total entries}</td>
            </tr>

            <tr id="BlR_[0-9]+" style="display: none>
                <!-- No idea why this is here, I guess for spacing -->
            </tr>

            <tr>
                <td>
                    <table class="... nested">
                        <tr>
                            <th class="blankCell"></th>
                            <th abbr="title">
                                {title not necessarily the same as the abbr
                                 attribute}
                            </th>
                            ...
                        </tr>

                        <!-- Each class time is listed in this format: -->
                        <tr>
                            <td class="blankCell"></th>
                            <td>{Instructor}</td>
                            <td>{Room}</td>
                            <td>{Days}</td>
                            <td>{Date (Weekly for all courses)}</td>
                            <td>{Start Time}</td>
                            <td>{End Time}</td>
                            <td>{Max Enr}</td>
                            <td>{Total Enr}</td>
                        </tr>

                        <!-- Rest of the class times -->
                    </table>
                </td>
            </tr>

            <!-- Rest of the courses -->
        </table>
    '''

    table = tree.xpath('//*[@id="mainBody"]/div[2]/table')[0]

    # As if the format is bad enough by itself, but CAMS makes it worse by
    # leaving out rows sometimes (for example, when the class times are not
    # known), so we have to store some parser state in order to do "error
    # handling"
    current_sect = None
    sections = []
    for row in table.xpath('tr'):
        if 'courseInfo' in row.classes:
            # Hedaer
            # Add the current_sect to the main list, but check if it is None
            # first in case there is some invalid parse
            if current_sect is not None:
                sections.append(current_sect)

            id, _, credits, start_date, end_date, cap, enr = \
                map(get_text, row.xpath('td'))
            # For courses currently offered, the title is wrapped in an anchor
            # element, though for non-existing ones, it is not, so we have to find
            # the text recursively
            title = row.xpath('td[2]/a')[0].text_content().strip()

            current_sect = {
                'id': parse_course_id(id),
                'title': title,
                'credits': int(credits),
                'startDate': parse_date(start_date),
                'endDate': parse_date(end_date),
                'sessions': [],
            }
        elif row.get('id', '')[0:4] == 'BlR_':
            # Random blank display: none row that's here for absolutely no
            # reason
            pass
        else:
            # Time info

            # Add in the time info to the section
            for class_row in row.xpath('td/table/tr[position() > 1]'):
                _, instructor, room, days, _, start_time, end_time, _, _ = \
                    map(get_text, class_row.xpath('td'))
                current_sect['sessions'].append({
                    'instructor': instructor,
                    'room': room,
                    'days': days,
                    'startTime': parse_time(start_time),
                    'endTime': parse_time(end_time),
                })

    return sections


def group_courses(sections):
    '''
    Processes the list of sections parsed from the scraper into a more useful
    format by grouping sections of the same course and flattening some
    structures.

    TODO Should sessions be split up so that each entry has only one day?
    '''

    courses = {}
    for sect in sections:
        # Copy sect['id'] to avoid mutating the original data
        id = sect['id'].copy()
        secNum = id.pop('section')
        idStr = str(id) # Stringify to use as a key into the courses dict
        if idStr not in courses:
            courses[idStr] = {
                **id,
                # We assume that the title and credits are the same for all
                # sections with the same base course identifier
                'title': sect['title'],
                'credits': sect['credits'],
                'sections': [],
            }

        courses[idStr]['sections'].append({
            'section': secNum,
            'startDate': sect['startDate'],
            'endDate': sect['endDate'],
            'sessions': sect['sessions'],
        })

    # Convert the dict into an array now that we don't need the keys any more
    # (the IDs are stored in each entry)
    return [courses[id] for id in courses]


def scrape_courses(username, password, term):
    form_data = {
        'txtUsername': username,
        'txtPassword': password,
        'term': term,
        'accessKey': '',
        'op': 'login'
    }

    session = requests.Session()

    r = session.post(
        'https://cams.floridapoly.org/student/ceProcess.asp',
        data=form_data)
    if r.status_code != 200:
        raise Error('Could not login')
    # TODO Error if the login cookies aren't returned

    # The first page can be retrieved via GET, but the rest have to be POSTed
    # and contain an access key returned in a form in the first page
    first_page = session.get(
        'https://cams.floridapoly.org/student/cePortalOffering.asp')

    first_page_tree = html.fromstring(first_page.text)

    # Get the accessKey
    accessKey = first_page_tree.xpath(
        '//form[@id="OptionsForm"]/input[@name="accessKey"]')[0].get('value')

    all_sections = parse_sections(first_page_tree)

    total_pages_text = first_page_tree.xpath(
        '//*[@id="mainBody"]/div[2]/div[1]/text()[last()]')[0]
    pages = int(re.search(r'Total Pages: (\d+)', total_pages_text).group(1))

    for page in range(2, pages + 1):
        offering_data = {
            'IsPostBack': 'True',
            'page': page,
            'accessKey': accessKey,
            'f_TermCalendarID': term,
            'f_Days': '',
            'f_TimeFrom': '',
            'f_TimeTo': '',
            'f_Campuses': '',
            'f_Departments': '',
            'f_Divisions': '',
            'TimeFrom': '',
            'TimeTo': '',
        }

        later_page = session.post(
            'https://cams.floridapoly.org/student/cePortalOffering.asp',
            data=offering_data)

        later_page_tree = html.fromstring(later_page.text)
        sections = parse_sections(later_page_tree)

        all_sections.extend(sections)

    # Logout (don't care about the responce)
    session.get('https://cams.floridapoly.org/student/logout.asp')

    return group_courses(all_sections)


def scrape_terms():
    '''
        Gets the mapping between term names and their numbers.
        This does not require login info, as the terms are listed on the login
        page.
    '''

    login_page = requests.get('https://cams.floridapoly.org/student/login.asp')

    login_page_tree = html.fromstring(login_page.text)


    terms = {}
    for term in login_page_tree.xpath('//*[@id="idterm"]/option'):
        terms[get_text(term)] = term.get('value')

    return terms


# main() function for executing the scraper locally
# TODO Remove this once the project is more stable
import json
import sys
def main(argv):
    username = argv[0]
    password = argv[1]

    # TODO Figure out what terms are valid
    # (19 is Fall 2017)
    term = len(argv) > 2 and argv[2] or 27

    courses = scrape_courses(username, password, term)
    print(json.dumps(courses, indent=2))

if __name__ == '__main__':
    main(sys.argv[1:])

