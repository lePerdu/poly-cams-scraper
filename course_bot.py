#!/usr/bin/env python

# course_bot.py
# Web bot for retrieving a list of courses from Florida Poly CAMS given login
# information

import re
import sys
from datetime import datetime
from pprint import pprint

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

def parse_date(date):
    return datetime.strptime(date, '%m/%d/%Y')

def parse_time(time):
    return datetime.strptime(time, '%I:%M:%S %p')

def parse_course_id(id):
    '''
    Parses a course identifier of the form:
        DEP<COURSE #>TYPE<SECTION #>
    Into a (departement, course, section) tuple
    '''

    # TODO What other suffixes are there besides C (for lab) and how can they
    # be differentiated from the type of course (i.e. GENMAT, ENGR)?
    dep, course, sec = re.match(r'(\w{3})(\w{4}C?)[^\d]+(\d+)?', id).groups()
    # Some course identifiers don't include the section, so we assume it's 1
    return (dep, course, sec and int(sec) or 1)


def parse_courses(tree):
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

    # Course identifier, title, cedit count, date range, and enrolment counts
    # are in one row, with the class "courseInfo"
    row1s = table.xpath('tr[position() mod 3 = 1]')

    # The rest of the information is in a sub-table in a separate row
    row2s = table.xpath('tr[position() mod 3 = 0]/td/table')

    courses = []
    for row1, row2 in zip(row1s, row2s):
        id, title, creds, start_date, end_date, cap, enr = \
            map(get_text, row1.xpath('td'))
        # The title is nested in an anchor element
        #title = get_text(row1.xpath('td[2]/a')[0])

        classes = []
        for class_row in row2.xpath('tr[position() > 1]'):
            _, instructor, room, days, _, start_time, end_time, _, _ = \
                map(get_text, class_row.xpath('td'))
            classes.append({
                'instructor': instructor,
                'room': room,
                'days': days,
                'times': (parse_time(start_time), parse_time(end_time)),
            })

        courses.append({
            'id': parse_course_id(id),
            'title': title,
            'credits': int(creds),
            'dates': (parse_date(start_date), parse_date(end_date)),
            'classes': classes
        })

    return courses


def scrape_courses(username, password, term):
    form_data = {
        'txtUsername': username,
        'txtPassword': password,
        'term': term,
        'accessKey': '',
        'op': 'login'
    }

    r = requests.post(
        'https://cams.floridapoly.org/student/ceProcess.asp',
        data=form_data)
    # TODO Error if the login cookies aren't returned

    # The first page can be retrieved via GET, but the rest have to be POSTed
    # and contain an access key returned in a form in the first page
    first_page = requests.get(
        'https://cams.floridapoly.org/student/cePortalOffering.asp',
        cookies=r.cookies)

    first_page_tree = html.fromstring(first_page.text)

    # Get the accessKey
    accessKey = first_page_tree.xpath(
        '//form[@id="OptionsForm"]/input[@name="accessKey"]')[0].get('value')

    all_courses = parse_courses(first_page_tree)

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

        later_page = requests.post(
            'https://cams.floridapoly.org/student/cePortalOffering.asp',
            data=offering_data,
            cookies=r.cookies)

        f = open('courses.html', 'w')
        f.write(later_page.text)
        f.close()

        later_page_tree = html.fromstring(later_page.text)
        courses = parse_courses(later_page_tree)

        all_courses.extend(courses)

    # Logout (don't care about the responce)
    requests.get(
        'https://cams.floridapoly.org/student/logout.asp',
         cookies=r.cookies)

    return all_courses



def main(argv):
    username = argv[0]
    password = argv[1]

    # TODO Figure out what terms are valid
    # (19 is Fall 2017)
    term = len(argv) > 2 and argv[2] or 19

    courses = scrape_courses(username, password, term)
    pprint(courses)


if __name__ == '__main__':
    main(sys.argv[1:])
