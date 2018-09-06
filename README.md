# FPSched

Class schedule generator for Florida Polytechnic University

## Running

This project requires python 3 has the dependencies:
* requests
* lxml

Run `pip install -r requirements.txt` to install these requirements
(preferably in a [virtual environment](
    https://packaging.python.org/guides/installing-using-pip-and-virtualenv/
)).

The script can be run with
`python scheduler.py <username> <password> [<term>]`,
using your normal Florida Poly login info. The term is the numerical identifier
for the term and the value will default to 27 (Fall 2018). The program will
retrieve a list of all courses in the term and then prompt for the ones you
wish to take (give the full identifier (i.e. MAC2312 or EEL3112C). It will then
print out a list of courses with their section numbers that do not overlap.

