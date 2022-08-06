#!/usr/bin/env python3
#
# Copyright (c) 2012 David Drake
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
#
# nasa_apod_desktop.py
# https://github.com/randomdrake/nasa-apod-desktop
#
# Written/Modified by David Drake
# http://randomdrake.com
# http://twitter.com/randomdrake
#
#
# Tested on Ubuntu 12.04
#
#
# DESCRIPTION
# 1) Grabs your current download path
# 2) Downloads the latest image of the day from NASA (http://apod.nasa.gov/apod/)
# 3) Determines your desktop resolution, or uses the set default.
# 4) Resizes the image to the given resolution.
# 5) Sets the image as your desktop.
# 6) Adds image to XML file used to scroll through desktop background images.
#
# It's not very exciting to scroll through a single image, so it will attempt to download
# additional images (default: 10) to seed your list of images.
#
#
# INSTALLATION
# Place the file wherever you like and chmod +x it to make it executable
# Ensure you have Python installed (default for Ubuntu) and the PIL and lxml packages:
# pip install -f requirements.txt or sudo apt-get install python-imaging python-lxml
#
#
# RUN AT STARTUP
# To have this run whenever you startup your computer, perform the following steps:
# 1) Click on the settings button (cog in top right)
# 2) Select "Startup Applications..."
# 3) Click the "Add" button
# 4) Enter whatever Name and Comment you like with the following Command:
# python /path/to/nasa_apod_desktop.py
# 5) Click on the "Add" button
#
# DEFAULTS
# While the script will detect as much as possible and has safe defaults, you may want to set your own.
#
# DOWNLOAD_PATH  - where you want the file to be downloaded. Will be auto-detected if not set.
# CUSTOM_FOLDER  - if we detect your download folder, this will be the target folder in there.
# RESOUTION_TYPE -
#     'stretch': single monitor or the combined resolution of your available monitors
#     'largest': largest resolution of your available monitors
#     'default': use the default resolution that is set
# RESOLUTION_X   - horizontal resolution if RESOLUTION_TYPE is not default or cannot be
#                  automatically determined
# RESOLUTION_Y   - vertical resolution if RESOLUTION_TYPE is not default or cannot be
#                  automatically determined
# RESIZE_TYPE    -
#     'none':    don't resize the image
#     'stretch': stretch and scale image to resolution ignoring the aspect ratio
#     'scale':   scale image maintaining aspect ratio
# PICTURE_OPTIONS - set the gnome picture-options setting
#     'reset':    reset the options
#     'centered': center and fit the full image
#     'zoom':     zoom image to fit the full screen
#     https://askubuntu.com/a/914760 for a full list
# NASA_APOD_SITE - location of the current picture of the day
# IMAGE_SCROLL   - if true, will write also write an XML file to make the images scroll
# IMAGE_DURATION - if IMAGE_SCROLL is enabled, this is the duration each will stay in seconds
# SEED_IMAGES    - if > 0, it will download previous images as well to seed the list of images
# SHOW_DEBUG     - print useful debugging information or statuses

from datetime import datetime, timedelta
from lxml import etree
from sys import exit
from sys import stdout
from PIL import Image
from PIL import ImageFile
from PIL import ImageOps
import glob
import random
import logging
import os
import re
import urllib.request
import subprocess
from gi.repository import GLib
DOWNLOAD_PATH = '/tmp/backgrounds/'
CUSTOM_FOLDER = 'nasa-apod-backgrounds'
RESOLUTION_TYPE = 'default'
RESOLUTION_X = 1920
RESOLUTION_Y = 1080
RESIZE_TYPE = 'scaled'
PICTURE_OPTIONS = 'centered'
NASA_APOD_SITE = 'http://apod.nasa.gov/apod/'
IMAGE_SCROLL = True
IMAGE_DURATION = 1200
SEED_IMAGES = 10
SHOW_DEBUG = True


# Use XRandR to grab the desktop resolution. If the scaling method is set to 'largest',
# we will attempt to grab it from the largest connected device. If the scaling method
# is set to 'stretch' we will grab it from the current value. Default will simply use
# what was set for the default resolutions.
def find_resolution():
    logging.info("RESOLUTION_TYPE:" + RESOLUTION_TYPE)

    if RESOLUTION_TYPE == 'default':
        logging.info(
            "Using default resolution of {}x{}".format(
                RESOLUTION_X, RESOLUTION_Y))
        return RESOLUTION_X, RESOLUTION_Y

    res_x = 0
    res_y = 0

    logging.info("Attempting to determine the current resolution.")
    if RESOLUTION_TYPE == 'largest':
        regex_search = 'connected'
    else:
        regex_search = 'current'

    p1 = subprocess.Popen(["xrandr"], stdout=subprocess.PIPE)
    p2 = subprocess.Popen(["grep", regex_search],
                          stdin=p1.stdout, stdout=subprocess.PIPE)
    p1.stdout.close()
    output = str(p2.communicate()[0])

    if RESOLUTION_TYPE == 'largest':
        # We are going to go through the connected devices and get the X/Y from
        # the largest
        matches = re.finditer(" connected ([0-9]+)x([0-9]+)+", output)
        if matches:
            largest = 0
            for match in matches:
                if int(match.group(1)) * int(match.group(2)) > largest:
                    res_x = match.group(1)
                    res_y = match.group(2)
        else:
            logging.warning("Could not determine largest screen resolution.")
    else:
        reg = re.search(".* current (.*?) x (.*?),.*", output)
        if reg:
            res_x = reg.group(1)
            res_y = reg.group(2)
        else:
            logging.warning("Could not determine current screen resolution.")

    # If we couldn't find anything automatically use what was set for the
    # defaults
    if res_x == 0 or res_y == 0:
        res_x = RESOLUTION_X
        res_y = RESOLUTION_Y
        logging.warning(
            "Could not determine resolution automatically. Using defaults.")

    logging.warning("Using detected resolution of {}x{}".format(res_x, res_y))

    return int(res_x), int(res_y)


# Uses GLib to find the localized "Downloads" folder
# See:
# http://askubuntu.com/questions/137896/how-to-get-the-user-downloads-folder-location-with-python
def set_download_folder():
    if DOWNLOAD_PATH:
        logging.info("Using default path for downloads:" + DOWNLOAD_PATH)
        return DOWNLOAD_PATH

    downloads_dir = GLib.get_user_special_dir(
        GLib.UserDirectory.DIRECTORY_DOWNLOAD)
    if downloads_dir:
        # Add any custom folder
        new_path = os.path.join(downloads_dir, CUSTOM_FOLDER)
        logging.info("Using automatically detected path:" + new_path)
        return new_path

    raise RuntimeError("Unable to determine download folder")


# Download HTML of the site
def download_site(url):
    logging.info("Downloading contents of the site to find the image name")
    req = urllib.request.Request(url)
    try:
        reply = urllib.request.urlopen(req).read()
    except urllib.error.HTTPError as error:
        logging.warning("Error downloading" + url + "-" + str(error.code))
        reply = "Error: " + str(error.code)
    return reply


# Finds the image URL and saves it
def get_image(text):
    logging.info("Grabbing the image URL")
    file_url, filename, file_size = get_image_info('a href', text)
    # If file_url is None, the today's picture might be a video
    if file_url is None:
        return None

    logging.info("Found name of image:" + filename)

    save_to = os.path.join(
        DOWNLOAD_PATH,
        os.path.splitext(filename)[0] +
        '.png')

    if not os.path.isfile(save_to):
        # If the response body is less than 500 bytes, something went wrong
        if file_size < 500:
            logging.warning(
                "Response less than 500 bytes, probably an error\nAttempting to just grab image source")
            file_url, filename, file_size = get_image_info('img src', text)
            # If file_url is None, the today's picture might be a video
            if file_url is None:
                return None
            logging.info("Found name of image:" + filename)
            if file_size < 500:
                # Give up
                logging.warning("Could not find image to download")
                exit()

        logging.info("Retrieving image")
        urllib.request.urlretrieve(
            file_url, save_to, print_download_status)

        logging.info("\nDone downloading " + human_readable_size(file_size))
    else:
        logging.info("File exists, moving on")

    return save_to


# Resizes the image to the provided dimensions
def resize_image(filename):
    logging.info("RESIZE_TYPE:" + RESIZE_TYPE)

    if RESIZE_TYPE == 'none':
        logging.info("Image resize skipped")
        return

    logging.info("Opening local image:" + filename)

    image = Image.open(filename)
    current_x, current_y = image.size
    if (current_x, current_y) == (RESOLUTION_X, RESOLUTION_Y):
        logging.info("Images are currently equal in size. No need to scale.")
    else:
        if RESIZE_TYPE == 'stretch':
            logging.info(
                "stretch: resizing the image from %sx%s to %sx%s",
                image.size[0],
                image.size[1],
                RESOLUTION_X,
                RESOLUTION_Y)
            image = image.resize((RESOLUTION_X, RESOLUTION_Y), Image.ANTIALIAS)
        else:
            logging.info(
                "scale: resizing the image from %sx%s to fit inside %sx%s maintaining aspect ratio",
                image.size[0],
                image.size[1],
                RESOLUTION_X,
                RESOLUTION_Y)
            image = ImageOps.contain(image, (RESOLUTION_X, RESOLUTION_Y))

        logging.info("Saving the image to" + filename)
        fhandle = open(filename, 'wb')
        image.save(fhandle, 'PNG')


# Sets the new image as the wallpaper
def set_gnome_wallpaper(file_path):
    logging.info("PICTURE_OPTIONS:" + PICTURE_OPTIONS)

    if PICTURE_OPTIONS == 'reset':
        command = "gsettings reset org.gnome.desktop.background picture-options"
    else:
        command = "gsettings set org.gnome.desktop.background picture-options " + PICTURE_OPTIONS
    status, output = subprocess.getstatusoutput(command)
    logging.info(command + ":" + str(status) + ":" + output)

    logging.info("Setting the image" + file_path)
    command = "gsettings set org.gnome.desktop.background picture-uri file://" + file_path
    status, output = subprocess.getstatusoutput(command)
    logging.info(command + ":" + str(status) + ":" + output)
    return status


def print_download_status(block_count, block_size, total_size):
    written_size = human_readable_size(block_count * block_size)
    total_size = human_readable_size(total_size)

    # Adding space padding at the end to ensure we overwrite the whole line
    stdout.write("\r%s bytes of %s         " % (written_size, total_size))
    stdout.flush()


def human_readable_size(number_bytes):
    for x in ['bytes', 'KB', 'MB']:
        if number_bytes < 1024.0:
            return "%3.2f%s" % (number_bytes, x)
        number_bytes /= 1024.0


# Creates the necessary XML so background images will scroll through
def create_desktop_background_scoll(filename):
    if not IMAGE_SCROLL:
        return filename

    logging.info("Creating XML file for desktop background switching.")

    filename = DOWNLOAD_PATH + '/nasa_apod_desktop_backgrounds.xml'

    # Create our base, background element
    background = etree.Element("background")

    # Grab our PNGs we have downloaded
    images = glob.glob(DOWNLOAD_PATH + "/*.png")
    num_images = len(images)

    if num_images < SEED_IMAGES:
        # Let's seed some images
        # Start with yesterday and continue going back until we have enough
        logging.info("Downloading some seed images as well")
        days_back = 0
        seed_images_left = SEED_IMAGES
        while seed_images_left > 0:
            days_back += 1
            logging.info(
                    "Downloading seed image (" +
                    str(seed_images_left) +
                    " left):")
            day_to_try = datetime.now() - timedelta(days=days_back)

            # Filenames look like /apYYMMDD.html
            seed_filename = NASA_APOD_SITE + "ap" + \
                day_to_try.strftime("%y%m%d") + ".html"
            seed_site_contents = download_site(seed_filename)

            # Make sure we didn't encounter an error for some reason
            if seed_site_contents == "error":
                continue

            seed_filename = get_image(seed_site_contents)
            # If the content was an video or some other error occurred, skip the
            # rest.
            if seed_filename is None:
                continue

            resize_image(seed_filename)

            # Add this to our list of images
            images.append(seed_filename)
            seed_images_left -= 1
        logging.info("Done downloading seed images")

    # Get our images in a random order so we get a new order every time we get
    # a new file
    random.shuffle(images)
    # Recalculate the number of pictures
    num_images = len(images)

    for i, image in enumerate(images):
        # Create a static entry for keeping this image here for IMAGE_DURATION
        static = etree.SubElement(background, "static")

        # Length of time the background stays
        duration = etree.SubElement(static, "duration")
        duration.text = str(IMAGE_DURATION)

        # Assign the name of the file for our static entry
        static_file = etree.SubElement(static, "file")
        static_file.text = images[i]

        # Create a transition for the animation with a from and to
        transition = etree.SubElement(background, "transition")

        # Length of time for the switch animation
        transition_duration = etree.SubElement(transition, "duration")
        transition_duration.text = "5"

        # We are always transitioning from the current file
        transition_from = etree.SubElement(transition, "from")
        transition_from.text = images[i]

        # Create our tranition to element
        transition_to = etree.SubElement(transition, "to")

        # Check to see if we're at the end, if we are use the first image as
        # the image to
        if i + 1 == num_images:
            transition_to.text = images[0]
        else:
            transition_to.text = images[i + 1]

    xml_tree = etree.ElementTree(background)
    xml_tree.write(filename, pretty_print=True)

    return filename


def get_image_info(element, text):
    # Grabs information about the image
    regex = '<' + element + '="(image.*?)"'
    reg = re.search(regex, str(text), re.IGNORECASE)
    if reg:
        if 'http' in reg.group(1):
            # Actual URL
            file_url = reg.group(1)
        else:
            # Relative path, handle it
            file_url = NASA_APOD_SITE + reg.group(1)
    else:
        logging.info("Could not find an image. May be a video today.")
        return None, None, None

    # Create our handle for our remote file
    logging.info("Opening remote URL")

    remote_file = urllib.request.urlopen(file_url)

    filename = os.path.basename(file_url)
    file_size = float(remote_file.headers.get("content-length"))

    return file_url, filename, file_size


if __name__ == '__main__':
    # Our program
    if SHOW_DEBUG:
        logging.basicConfig(level=logging.INFO)

    logging.info("Starting")

    # Find desktop resolution
    RESOLUTION_X, RESOLUTION_Y = find_resolution()

    # Set a localized download folder
    DOWNLOAD_PATH = set_download_folder()

    # Create the download path if it doesn't exist
    if not os.path.exists(os.path.expanduser(DOWNLOAD_PATH)):
        os.makedirs(os.path.expanduser(DOWNLOAD_PATH))

    # Grab the HTML contents of the file
    site_contents = download_site(NASA_APOD_SITE)
    if site_contents == "error":
        logging.error("Could not contact site.")
        exit()

    # Download the image
    filename = get_image(site_contents)
    if filename is not None:
        # Resize the image
        resize_image(filename)

    # Create the desktop switching xml
    filename = create_desktop_background_scoll(filename)
    # If the script was unable todays image and IMAGE_SCROLL is set to False,
    # the script exits
    if filename is None:
        logging.warning("Today's image could not be downloaded.")
        exit()

    # Set the wallpaper
    status = set_gnome_wallpaper(filename)
    logging.info("Finished!")
