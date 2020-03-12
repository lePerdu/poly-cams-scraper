#!/usr/bin/env python

## scraper.py
# Functions for scraping data from the CAMS portal
#

import asyncio
import re
from datetime import datetime

import aiohttp
from lxml import html

CAMS_LOGIN_PAGE_URL = 'https://cams.floridapoly.org/student/login.asp'
CAMS_LOGIN_URL = 'https://cams.floridapoly.org/student/ceProcess.asp'
CAMS_COURSE_PAGE_URL = \
    'https://cams.floridapoly.org/student/cePortalOffering.asp'
CAMS_LOGOUT_URL = 'https://cams.floridapoly.org/student/logout.asp'


class AuthError(Exception):
    """Error type for authentication errors."""
    pass


def parse_jsonish(jsonish):
    """Parses the retarded data format CAMS uses.
    It could 100% be JSON, but instead it:
    - Is wrapped in parentheses
    - Uses single quotes
    - Uses `new Date(<date string (in non-standard format)>)`
    - Quotes booleans (still valid JSON, but annoying and pointless)

    (The CAMS page calls `eval()` on the responses)
    """
    stripped = jsonish[1:-1]
    double_quotes = re.sub("'", '"', stripped)
    actual_json = re.sub(r'new Date\(("[^"]*")\)', r'\1', double_quotes)
    with_bools = re.sub('"false"', 'false', actual_json)
    return json.loads(with_bools)


def pairs_to_dict(pairs):
    return {k: v for k, v in pairs if k}


def get_attr(attrs, name):
    for k, v in attrs:
        if k == name: return v
    return None


def get_text(elem):
    return elem.text.strip()


def parse_date(datestr):
    """Parses a date in the format %m/%d/%Y into a POSIX timestamp.
    TODO Should this output in ISO format instead?
    """
    return int(datetime.strptime(datestr, '%m/%d/%Y').timestamp())


def parse_time(timestr):
    """Parses a time in the format %H:%M:%S into a POSIX timestamp.
    (number of seconds from the start of the day)
    TODO Should this output in ISO format instead?
    """

    # strptime uses 1900-01-01 as the default date, so subtract it out to get
    # the timestamp from the start of the day
    return int((datetime.strptime(timestr, '%I:%M:%S %p')
          - datetime(1900, 1, 1)).total_seconds())


def parse_course_id(id):
    """Parses a course identifier.
    These are in the form:
        DEP<COURSE #>TYPE<SECTION #>
    Into a (department, course, section) tuple

    Note: Some older courses do not have a type field or section
    """

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
    """Scrapes the section list from the HTML.
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
                            <td class="blankCell"></td>
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
    """

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
            # element, though for non-existing ones, it is not, so we have to
            # find all text inside nested elements
            title = row.xpath('td[2]')[0].text_content().strip()

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
    """Processes the list of sections parsed from the scraper into a more useful
    format by grouping sections of the same course and flattening some
    structures.

    TODO Should sessions be split up so that each entry has only one day?
    """

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


async def scrape_course_page(session, access_key, term, page):
    page_data = {
        'IsPostBack': 'True',
        'page': page,
        'accessKey': access_key,
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

    async with session.post(CAMS_COURSE_PAGE_URL, data=page_data) as resp:
        page_tree = html.fromstring(await resp.text())

    return parse_sections(page_tree)


async def scrape_courses(username, password, term):
    login_form_data = {
        'txtUsername': username,
        'txtPassword': password,
        'term': term,
        'accessKey': '',
        'op': 'login'
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(
            CAMS_LOGIN_URL, data=login_form_data) as login_resp:

            login_data = parse_jsonish(await login_resp.text())

        if not login_data['loginStatus']:
            raise Exception(login_data['strError'])

        # The first page can be retrieved via GET, but the rest have to be POSTed
        # and contain an access key returned in a form in the first page
        async with session.get(CAMS_COURSE_PAGE_URL) as first_page_resp:
            first_page_tree = html.fromstring(await first_page_resp.text())

        # Get the accessKey
        access_key = first_page_tree.xpath(
            '//form[@id="OptionsForm"]/input[@name="accessKey"]'
        )[0].get('value')

        all_sections = parse_sections(first_page_tree)

        total_pages_text = first_page_tree.xpath(
            '//*[@id="mainBody"]/div[2]/div[1]/text()[last()]')[0]
        page_count = int(re.search(
            r'Total Pages: (\d+)', total_pages_text).group(1))

        # Fetch the rest of the pages asynchronously all at once
        later_page_sections = await asyncio.gather(*(
            scrape_course_page(session, access_key, term, page)
            for page in range(2, page_count + 1)
        ))

        # Logout (don't care about the responce)
        async with session.get(CAMS_LOGOUT_URL):
            pass

    for s in later_page_sections:
        all_sections.extend(s)

    return group_courses(all_sections)


async def scrape_terms():
    """Gets the mapping between term names and their numbers.
    This does not require login info, as the terms are listed on the login
    page.
    """

    async with aiohttp.ClientSession() as session:
        async with session.get(CAMS_LOGIN_PAGE_URL) as login_page:
            login_page_tree = html.fromstring(await login_page.text())

    terms = {}
    for term in login_page_tree.xpath('//*[@id="idterm"]/option'):
        terms[get_text(term)] = term.get('value')

    return terms


async def scrape_latest_term():
    """Gets the most recent term available."""
    terms = await scrape_terms()
    return max(terms.values())


# main() function for executing the scraper locally
# TODO Remove this once the project is more stable
import json
import sys
async def main():
    username = sys.argv[1]
    password = sys.argv[2]

    # Use the latest term if not provided
    if len(sys.argv) > 3:
        term = sys.argv[3]
    else:
        term = await scrape_latest_term()

    courses = await scrape_courses(username, password, term)
    print(json.dumps(courses, indent=2))


if __name__ == '__main__':
    asyncio.run(main())
