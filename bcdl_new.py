# all the selenium goodies
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver import ActionChains

# selenium exceptions
from selenium.common.exceptions import NoSuchElementException
from selenium.common.exceptions import ElementNotInteractableException

# TODO: can probably utilize selenium's sleep/wait functions instead;
#       need to research them more
from time import sleep

# regex
import re

# sqlite3
import sqlite3

# has it been TIMEOUT seconds without a change in the page? then it
# is loaded.
TIMEOUT = 10

# for debug messages & limiting number of albums to load
DEBUG = True
MAX_ALBUMS = 100

if (DEBUG):
    debug_file = open('debug_log', 'a')

DB_LOCATION = "bcdl_new.db"


def main():
    create_db()
    driver = webdriver.Firefox()

    # this URL will automatically bring us to the user's collection
    # after signing in
    driver.get("https://bandcamp.com/login?from=fan_page")

    username_field = driver.find_element(by=By.NAME, value="username-field")
    password_field = driver.find_element(by=By.NAME, value="password-field")

    # TODO: grab these from either the command line, or allow the user to sign
    #       in on their own w/ the window

    user = ''
    pword = ''
    if (DEBUG):
        with open('user_pass', 'r') as login:
            user = login.readline()
            pword = login.readline()
    username_field.send_keys(user)
    password_field.send_keys(pword)

    password_field.send_keys(Keys.RETURN)

    driver.implicitly_wait(10)

    # check to see if we're signed in every 5 seconds. it's the user's
    # responsibility to solve any captchas or correct any incorrect passwords
    loaded = False
    while (not loaded):
        try:
            show_more_button = driver.find_element(by=By.CLASS_NAME,
                                                   value="show-more")
            loaded = True
            # TODO: need to verify button clicking try/except stuffs is good
            # 2/11 update: tbh it's hacky but probably fine to call it done
            show_more_button.click()
            show_more_button.click()
        except NoSuchElementException:
            log("INFO", "No luck, waiting 5sec and trying again")
            sleep(5)
        except ElementNotInteractableException:
            # explanation: generally we need 2 button clicks to load the
            # additional elements. however, it seems that sometimes a single
            # click is enough. if we hit this exception, it means that
            # the webdriver was able to find the element, however after 0 or 1
            # clicks, it is no longer able to find it anymore. this -probably-
            # means that the additional elements have been loaded, therefore
            # we no longer need to click and we can just continue on as if
            # nothing happened
            log("INFO", "Failure with button clicking but i -think- we can continue..")

    # search for <li> blocks with an id that starts with ...
    xpath = "//li[contains(@id, 'collection-item-container_')]"

    # scroll down once every second until the page is fully loaded in.
    # once the page is loaded in, the 'elements' variable will contain
    # a list of every album to parse through
    current_album_count = 1
    previous_album_count = 0
    seconds_counter = 0
    actions = ActionChains(driver)
    while (True):

        elements = driver.find_elements(by=By.XPATH, value=xpath)
        current_album_count = len(elements)

        if (previous_album_count == current_album_count):
            break
        elif (current_album_count > MAX_ALBUMS):
            break

        # TODO: i believe the number of keypresses needed is going to change
        #       depending on the size of the window; maybe i'll have to whip
        #       up some sort of equation that takes window height as input
        #       and spits out the number of keypresses required
        actions.send_keys(Keys.PAGE_DOWN)
        actions.send_keys(Keys.PAGE_DOWN)
        actions.send_keys(Keys.PAGE_DOWN)
        actions.perform()

        seconds_counter += 1
        sleep(1)

        if seconds_counter > TIMEOUT:
            log('INFO', 'resetting seconds_counter; previous/current: ' +
                f'{previous_album_count}/{current_album_count}')

            previous_album_count = current_album_count
            seconds_counter = 0

    # if we've reached htis point, our page is all loaded in and we simply need
    # to begin parsing it

    grab_artist_regex = '(?<=by ).+?(?=\n)'
    grab_popularity_regex = '(?<=appears in ).+?(?= )'

    # BUG: the artist regex and looking for 'PRIVATE' can fail due to:
    #      1. the name of a song/etc could contain 'PRIVATE,' setting this to True
    #      2. the 'by ' could match more than one thing
    #      proposed fixes:- perhaps regex for a string strictly named '\nPRIVATE\n'
    #                     - count 'by ' matches; if there is more than one then
    #                       probably check album, if album is no then use
    #                       first match
    for element in elements:
        # scrape album_name
        # BUG: album_name will return NULL if it's a fanclub release
        album_name = element.get_attribute("data-title")

        # scrape artist_name
        # BUG: (see bug description above for block)
        artist_name = re.findall(grab_artist_regex, element.text)[0]

        # scrape popularity score
        try:
            popularity = []
            popularity = re.findall(grab_popularity_regex, element.text)
            if len(popularity) > 0:
                popularity = int(popularity[0])
            else:
                popularity = 0
        except:
            popularity = 0

        # scrape whether or not the album is private
        # BUG: (see bug description above for block)
        if 'PRIVATE' in element.text:
            is_private = 1
        else:
            is_private = 0

        log('INFO', f'artist: {artist_name}, album name: {album_name}, '
            f'private: {is_private}, popularity: {popularity}')
        if 'download' in element.text:
            # first download_page is a 'download' element
            download_page = element.find_element(by=By.PARTIAL_LINK_TEXT,
                                                 value='download')
            # then download_page is converted to a string, containing the link
            download_page = download_page.get_attribute("href")
            log('', download_page)
            add_to_db(artist_name, album_name, popularity, is_private, download_page)
        else:
            log("ERROR", f"no download present in {element.text}")
        log('', '---------------------')

    driver.quit()


def create_db():
    '''Creates a table named ALBUM with the properties
       artist, album, download, popularity
       if it does not already exist'''
    con = sqlite3.connect(DB_LOCATION)
    cur = con.cursor()
    res = cur.execute("SELECT name FROM sqlite_master")
    if (not res.fetchone()):
        log("INFO", "making db")
        # TODO: should be typing column names, ie: artist_name TEXT popularity INTEGER etc
        run_string = "CREATE TABLE ALBUM(artist_name TEXT, album_name TEXT, popularity INTEGER, is_private INTEGER, download_page TEXT)"
        cur.execute(run_string)


# TODO: maybe rename this function
def dl_page_in_db(download_page):
    con = sqlite3.connect(DB_LOCATION)
    cur = con.cursor()
    res = cur.execute(f"SELECT download_page FROM ALBUM WHERE download_page='{download_page}'")
    if (not res.fetchall()):
        log('INFO', f'{download_page} was not in db, returning False')
        con.close()
        return False
    log('INFO', f'{download_page} was in db, returning True')
    con.close()
    return True


def add_to_db(artist_name, album_name, popularity, is_private, download_page):
    # TODO: can bring con and cur outside of the scope of this function &
    # expose it to the rest of the script, instead of constantly open/close
    con = sqlite3.connect(DB_LOCATION)
    cur = con.cursor()
    data = [artist_name, album_name, popularity, is_private, download_page]
    if (not dl_page_in_db(download_page)):
        cur.execute("INSERT INTO ALBUM VALUES(?, ?, ?, ?, ?)", data)
        con.commit()
        con.close()
        log('INFO', f'{album_name} added to db')
        return True
    else:
        log('INFO', f'{album_name} failed to add to db; probably already in there')
        con.close()
        return False
    log('ERROR, 'f'something went wrong while adding {album_name}!!!')
    con.close()
    return False


def print_db():
    con = sqlite3.connect(DB_LOCATION)
    cur = con.cursor()
    res = cur.execute("SELECT artist_name FROM ALBUM")
    print(res.fetchall())

    download_pages = list()
    print_list = list()
    index = 1
    search_string = 'SELECT artist_name, album_name, popularity, '
    search_string += 'is_private, download_page FROM ALBUM ORDER BY popularity DESC'

    download_pages.append(None)  # fix index

    for (artist_name, album_name, popularity, is_private,
         download_page) in cur.execute(search_string):
        download_pages.append(download_page)
        print_list.append(f'{index} - {artist_name} - {album_name} ({popularity})')
        index += 1

    for item in print_list[::-1]:
        print(item)

    con.close()


def log(type, message):
    '''Print and record a debug message'''
    message = str(type) + ': ' + str(message)
    if (DEBUG):
        print(message)
        debug_file.write(message + '\n')


if __name__ == "__main__":
    main()
    print_db()
    if (DEBUG):
        debug_file.close()
