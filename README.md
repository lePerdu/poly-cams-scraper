# poly-cams-scraper

Scraper for the Florida Polytechnic University CAMS system.

## Running

This project requires python 3 has the dependencies:
* `requests`
* `lxml`
* `flask` (only for the webserver)

Run `pipenv install` to install these requirements

### Webserver

The webserver can be run with `pipenv run python app.py`. It has the following
API methods:
* GET `/terms` - Returns a JSON object mapping term names (i.e. "Fall 2018") to
  term IDs used by other API methods.
* GET `/courses` - Returns a JSON array of objects describing the available
  courses for a given term. The username and password are passed via HTTP Basic
  Authentication and the term is passed via the `term` URL parameter.

Endpoints can be suffixed with `?pretty=true` to make them return JSON pretty-
printed instead of minimized.

The server doesn't store or cache any information, so authentication is
required each time and it may take a few seconds to retrieve the list of
courses.

### Course Scraper

Courses can be scrapped locally by running:
`pipenv run python scraper.py <username> <password> [<term>]`
The output format is as above.

### Schedule Generator

A primitive interactive command-line script `scheduler.py` can be run which
will prompt for a list of courses and output all possible schedules for the
term with those courses. The program will retrieve a list of all courses in the
term and then prompt for the ones you wish to take (give the full identifier
(i.e. MAC2312 or EEL3112C). It will then print out a list of courses with their
section numbers that do not overlap.

## License

[The Unlicense](unlicense.org)

