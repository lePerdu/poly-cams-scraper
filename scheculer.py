#!/usr/bin/env python

## Class schedule generator

import sys
from itertools import *

from course_bot import scrape_courses

def conflicts(c1, c2):
    for cl1, cl2 in product(c1['classes'], c2['classes']):
        # See if the days collide
        if any(d1 == d2 for d1 in cl1['days'] for d2 in cl2['days']):
            t1, t2 = cl1['times'], cl2['times']
            # See if the times overlap
            # (start1 before end2 and end1 after start2)
            if t1[0] <= t2[1] and t1[1] >= t2[0]:
                return True

    return False


def print_schedules(all_courses, names):
    # Filter courses to those with ids in the names parameter (combination of
    # the departement and the course number).
    # Also group courses by course ID (i.e. the array is of sections of each
    # course)
    course_groups = {}
    for c in all_courses:
        dep, id, sec = c['id']

        name = dep + id
        if any(map(lambda n: n == name, names)):
            if name in course_groups:
                course_groups[name].append(c)
            else:
                course_groups[name] = [c]

    # Each element is a list of the sections of a certain course
    sections = (cs for _, cs in course_groups.items())

    # Take one section of each course
    # (The iterators are turned into lists so that iterating over them doesn't
    # consume them)
    for possible in map(list, product(*sections)):
        # Make sure no pair conflicts
        if not any(conflicts(c1, c2) for c1, c2 in combinations(possible, 2)):
            for c in possible:
                print(c['id'], end=', ')
            print()



def main(argv):
    username = argv[0]
    password = argv[1]

    # TODO Figure out what terms are valid
    # (19 is Fall 2017)
    # (27 is Fall 2018)
    term = len(argv) > 2 and argv[2] or 27

    print('Retrieving courses')
    global all_courses
    all_courses = scrape_courses(username, password, term)

    print('Input desired courses (separated by newlines): ')
    desired = []
    while True:
        name = input().strip()
        if name:
            desired.append(name)
        else:
            break

    print('Possible schedules:')
    print_schedules(all_courses, desired)


if __name__ == '__main__':
    main(sys.argv[1:])

