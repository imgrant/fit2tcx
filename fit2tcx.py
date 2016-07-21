#!/usr/bin/env python
#
# fit2tcx - convert a FIT file to a TCX file
#
# Copyright (c) 2012, Gustav Tiger <gustav@tiger.name> [https://github.com/Tigge/FIT-to-TCX/]
# Copyright (c) 2014-2016, Ian Grant <ian@iangrant.me> [https://github.com/imgrant/fit2tcx]
#
# Permission is hereby granted, free of charge, to any person obtaining a
# copy of this software and associated documentation files (the "Software"),
# to deal in the Software without restriction, including without limitation
# the rights to use, copy, modify, merge, publish, distribute, sublicense,
# and/or sell copies of the Software, and to permit persons to whom the
# Software is furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
# FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
# DEALINGS IN THE SOFTWARE.

__version__ = "1.6"

import sys
import copy
import contextlib
import argparse
import lxml.etree

from datetime import datetime, timedelta
from pytz import timezone, utc

from tzwhere import tzwhere
from geopy.distance import GreatCircleDistance

from fitparse import FitFile, FitParseError


"""
Limit values for error checking on speed & distance calculations
"""
# Speed and distance calculated from GPS will be ignored
# for trackpoints where the acceleration from the last
# point is above this threshold (in m/s^2)
MAX_ACCELERATION = 3.0


"""
FIT to TCX values mapping
"""

LAP_TRIGGER_MAP = {
    "manual":             "Manual",
    "time":               "Time",
    "distance":           "Distance",
    "position_start":     "Location",
    "position_lap":       "Location",
    "position_waypoint":  "Location",
    "position_marked":    "Location",
    "session_end":        "Manual",
    "fitness_equipment":  "Manual"}

INTENSITY_MAP = {
    "active":   "Active",
    "warmup":   "Active",
    "cooldown": "Active",
    "rest":     "Resting",
    None:       "Active"}

PRODUCT_MAP = {
    0:      "Unknown",
    255:    "Run Trainer 2.0",      # Timex
    # Garmin products:
    1:      "Garmin Connect API",   # Also HRM1
    2:      "AXH01",
    2:      "AXH01",
    4:      "AXB02",
    5:      "HRM2SS",
    6:      "DSI_ALF02",
    473:    "Forerunner 301",
    474:    "Forerunner 301",
    475:    "Forerunner 301",
    494:    "Forerunner 301",
    717:    "Forerunner 405",
    987:    "Forerunner 405",
    782:	"Forerunner 50",
    988:	"Forerunner 60",
    1011:	"DSI_ALF01",
    1018:   "Forerunner 310XT",
    1446:   "Forerunner 310XT",
    1036:   "Edge 500",
    1199:   "Edge 500",
    1213:   "Edge 500",
    1387:   "Edge 500",
    1422:   "Edge 500",
    1124:   "Forerunner 110",
    1274:   "Forerunner 110",
    1169:	"Edge 800",
    1333:	"Edge 800",
    1334:	"Edge 800",
    1497:	"Edge 800",
    1386:	"Edge 800",
    1253:	"Chirp",
    1325:	"Edge 200",
    1555:	"Edge 200",
    1328:	"Forerunner 910XT",
    1537:	"Forerunner 910XT",
    1600:	"Forerunner 910XT",
    1664:	"Forerunner 910XT",
    1765:	"Forerunner 920XT",
    1341:	"ALF04",
    1345:	"Forerunner 610",
    1410:	"Forerunner 610",
    1360:	"Forerunner 210",
    1436:	"Forerunner 70",
    1461:	"AMX",
    1482:	"Forerunner 10",
    1688:	"Forerunner 10",
    1499:	"Swim",
    1551:	"Fenix",
    1967:	"Fenix 2",
    1561:	"Edge 510",
    1742:	"Edge 510",
    1821:	"Edge 510",
    1567:	"Edge 810",
    1721:	"Edge 810",
    1822:	"Edge 810",
    1823:	"Edge 810",
    1836:	"Edge 1000",
    1570:	"Tempe",
    1735:	"VIRB Elite",
    1736:	"Edge Touring",
    1752:	"HRM Run",
    10007:	"SDM4",
    20119:	"Training Center",
    1623:	"Forerunner 620",
    2431:   "Forerunner 235"}


"""
TCX schema and namespace values
"""

TCD_NAMESPACE = "http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2"
TCD = "{%s}" % TCD_NAMESPACE

XML_SCHEMA_NAMESPACE = "http://www.w3.org/2001/XMLSchema-instance"
XML_SCHEMA = "{%s}" % XML_SCHEMA_NAMESPACE

SCHEMA_LOCATION = \
    "http://www.garmin.com/xmlschemas/ActivityExtension/v2 " + \
    "http://www.garmin.com/xmlschemas/ActivityExtensionv2.xsd " + \
    "http://www.garmin.com/xmlschemas/FatCalories/v1 " + \
    "http://www.garmin.com/xmlschemas/fatcalorieextensionv1.xsd " + \
    "http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2 " + \
    "http://www.garmin.com/xmlschemas/TrainingCenterDatabasev2.xsd"

NSMAP = {
    None: TCD_NAMESPACE,
    "xsi": XML_SCHEMA_NAMESPACE}



# Class and context manager to suppress stdout for use with tzwhere.
class DummyFile(object):
    def write(self, x): pass

@contextlib.contextmanager
def nostdout():
    save_stdout = sys.stdout
    sys.stdout = DummyFile()
    yield
    sys.stdout = save_stdout


class MyDataProcessor(object):

    """
    Custom units data processor for FIT object
    """
        
    def process_type_bool(self, field_data):
        if field_data.value is not None:
            field_data.value = bool(field_data.value)

    def process_type_date_time(self, field_data):
        value = field_data.value
        if value is not None and value >= 0x10000000:
            dt = datetime.utcfromtimestamp(631065600 + value)
            field_data.value = utc.normalize(dt.replace(tzinfo=utc))
            field_data.units = None  # Units were 's', set to None

    def process_type_local_date_time(self, field_data):
        if field_data.value is not None:
            dt = datetime.fromtimestamp(631065600 + field_data.value)
            field_data.value = utc.normalize(dt.replace(tzinfo=utc))
            field_data.units = None

    def process_units_semicircles(self, field_data):
        if field_data.value is not None:
            field_data.value *= 180.0 / (2**31)
        field_data.units = 'deg'


class TZDataProcessor(MyDataProcessor):

    """
    Extra data processor layer for working with timezones.
    For the Timex Run Trainer 2.0, date-times claim to be UTC (as per the FIT 
    format spec), but are actually an (unknown) local timezone.
    If the data processor is called with a lat,lon point, we look up the true
    timezone and re-normalize date-times to UTC.
    Otherwise, if the data processor is called with a timezone name (defaults
    to UTC, i.e. no difference), we use that and re-normalize.
    """

    def __init__(self, lat=None, lon=None, tzname="UTC"):
        if lat is not None and lon is not None:
            with nostdout():
                w = tzwhere.tzwhere()
            self.tz = timezone(w.tzNameAt(lat, lon))
        else:
            self.tz = timezone(tzname)

    def process_type_date_time(self, field_data):
        value = field_data.value
        if value is not None and value >= 0x10000000:
            dt = datetime.utcfromtimestamp(631065600 + value)
            dt = self.tz.localize(dt)
            field_data.value = utc.normalize(dt)
            field_data.units = None  # Units were 's', set to None

    def process_type_local_date_time(self, field_data):
        if field_data.value is not None:
            dt = datetime.fromtimestamp(631065600 + field_data.value)
            dt = self.tz.localize(dt)
            field_data.value = utc.normalize(dt)
            field_data.units = None  # Units were 's', set to None


def iso_Z_format(dt):
    iso = dt.isoformat()
    z_iso = iso.replace("+00:00", "Z")
    return z_iso


def sum_distance(activity,
                 start_time=datetime(1899, 1, 1, 0, 0, 1, tzinfo=utc),
                 end_time=datetime(2189, 12, 31, 23, 59, 59, tzinfo=utc)):
    """
    Calculate distance from GPS data for an activity
    """
    # First build tps array (using timestamp as the index)
    # in order to coalesce values at the same timepoint
    # under a single trackpoint element
    tps = {}
    fit_epoch = datetime(1989, 12, 31, 0, 0, 0, tzinfo=utc)
    for trackpoint in activity.get_messages('record'):
        tts = trackpoint.get_value("timestamp")
        tsi = int((tts - fit_epoch).total_seconds())
        if tps.get(tsi) is None:
            tps[tsi] = {
                'timestamp':        tts,
                'distance':         None,
                'position_lat':     None,
                'position_long':    None}
        for var in ['distance',
                    'position_lat',
                    'position_long']:
            if trackpoint.get_value(var) is not None:
                tps[tsi][var] = trackpoint.get_value(var)

    # For mid-activity laps, iterate through trackpoints to
    # grab the first point before the start of the lap, also
    # delete points that are not part of the lap
    prev = None
    for timestamp in sorted(tps, reverse=True):
        tp = tps[timestamp]
        if tp['timestamp'] < start_time and prev is None:
            prev = copy.copy(tp)
        if tp['timestamp'] < start_time or tp['timestamp'] > end_time:
            del tps[timestamp]

    # Then loop over tps array to calculate cumulative point-to-point
    # distance from GPS data. Existing distance data (e.g. from footpod)
    # is used when there is no GPS position available or it is bad.
    distance = 0.0
    for timestamp in sorted(tps):
        tp = tps[timestamp]
        if prev is not None:
            if prev['distance'] is None:
                prev_dist = 0
            else:
                prev_dist = prev['distance']
            if not None in (tp['position_lat'],
                            tp['position_long'],
                            prev['position_lat'],
                            prev['position_long']):
                try:
                    tp_timedelta = (tp['timestamp'] -
                                    prev['timestamp']).total_seconds()
                    gps_dist = GreatCircleDistance(
                        (tp['position_lat'],
                         tp['position_long']),
                        (prev['position_lat'],
                         prev['position_long'])
                    ).meters
                    gps_speed = (gps_dist / tp_timedelta)
                    # Fallback to existing distance/speed stream data
                    # if the GPS data looks erroneous (acceleration test)
                    if (gps_speed / tp_timedelta) > MAX_ACCELERATION:
                        gps_dist = tp['distance'] - prev_dist
                except:
                    # Fallback to existing distance stream data on error
                    gps_dist = tp['distance'] - prev_dist
            else:
                # Fallback to existing distance stream data if no GPS coords
                gps_dist = tp['distance'] - prev_dist
                
            distance += gps_dist
        prev = tp

    return distance


def create_element(tag, text=None, namespace=None):
    """Create a free element"""
    namespace = NSMAP[namespace]
    tag = "{%s}%s" % (namespace, tag)
    element = lxml.etree.Element(tag, nsmap=NSMAP)
    if text is not None:
        element.text = text
    return element


def create_sub_element(parent, tag, text=None, namespace=None):
    """Create an element as a child of an existing given element"""
    element = create_element(tag, text, namespace)
    parent.append(element)
    return element


def create_document():
    """Create a TCX XML document"""
    document = create_element("TrainingCenterDatabase")
    document.set(XML_SCHEMA + "schemaLocation", SCHEMA_LOCATION)
    document = lxml.etree.ElementTree(document)
    return document


def add_author(document):
    """Add author element (TCX writer) to TCX"""
    author = create_sub_element(document.getroot(), "Author")
    author.set(XML_SCHEMA + "type", "Application_t")
    create_sub_element(author, "Name", "fit2tcx Converter")
    build = create_sub_element(author, "Build")
    version = create_sub_element(build, "Version")
    vMajor, vMinor = tuple(map(int, (__version__.split("."))))
    create_sub_element(version, "VersionMajor", str(vMajor))
    create_sub_element(version, "VersionMinor", str(vMinor))
    create_sub_element(version, "BuildMajor", "0")
    create_sub_element(version, "BuildMinor", "0")
    create_sub_element(author, "LangID", "en")
    create_sub_element(author, "PartNumber", "000-00000-00")


def add_creator(element, manufacturer, product_name, product_id, serial):
    """Add creator element (recording device) to TCX activity"""
    creator = create_sub_element(element, "Creator")
    creator.set(XML_SCHEMA + "type", "Device_t")
    create_sub_element(creator, "Name", manufacturer + " " + product_name)
    unitID = int(serial or 0)
    create_sub_element(creator, "UnitId", str(unitID))
    # Set ProductID to 0 for non-Garmin devices
    if manufacturer != "Garmin":
        product_id = 0
    create_sub_element(creator, "ProductID", str(product_id))
    version = create_sub_element(creator, "Version")
    create_sub_element(version, "VersionMajor", "0")
    create_sub_element(version, "VersionMinor", "0")
    create_sub_element(version, "BuildMajor", "0")
    create_sub_element(version, "BuildMinor", "0")


def add_notes(element, text):
    """Add notes element to TCX activity"""
    create_sub_element(element, "Notes", text)


def add_trackpoint(element, trackpoint, sport):
    """Create a trackpoint element"""

    timestamp = trackpoint['timestamp']
    pos_lat = trackpoint['position_lat']
    pos_long = trackpoint['position_long']
    distance = trackpoint['distance']
    altitude = trackpoint['altitude']
    speed = trackpoint['speed']
    heart_rate = trackpoint['heart_rate']
    cadence = trackpoint['cadence']

    create_sub_element(element, "Time", iso_Z_format(timestamp))

    if pos_lat is not None and pos_long is not None:
        pos = create_sub_element(element, "Position")
        create_sub_element(pos, "LatitudeDegrees", "{:.6f}".format(pos_lat))
        create_sub_element(pos, "LongitudeDegrees", "{:.6f}".format(pos_long))

    if altitude is not None:
        create_sub_element(element, "AltitudeMeters", str(altitude))
    if distance is not None:
        create_sub_element(element, "DistanceMeters", str(distance))

    if heart_rate is not None:
        heartrateelem = create_sub_element(element, "HeartRateBpm")
        heartrateelem.set(XML_SCHEMA + "type", "HeartRateInBeatsPerMinute_t")
        create_sub_element(heartrateelem, "Value", str(heart_rate))

    if speed is not None or cadence is not None:
        if cadence is not None and sport == "Biking":
            # Bike cadence is stored in main trackpoint element,
            # not an extension, unlike running cadence (below)
            create_sub_element(element, "Cadence", str(cadence))
        exelem = create_sub_element(element, "Extensions")
        tpx = create_sub_element(exelem, "TPX")
        tpx.set("xmlns",
                "http://www.garmin.com/xmlschemas/ActivityExtension/v2")
        if speed is not None:
            create_sub_element(tpx, "Speed", str(speed))
        if cadence is not None:
            if sport == "Running":
                tpx.set("CadenceSensor", "Footpod")
                create_sub_element(tpx, "RunCadence", str(cadence))
            elif sport == "Biking":
                tpx.set("CadenceSensor", "Bike")


def add_lap(element,
            activity,
            lap,
            sport,
            dist_recalc,
            speed_recalc,
            calibrate,
            current_cal_factor,
            per_lap_cal,
            fixed_distance,
            activity_scaling_factor,
            total_cumulative_distance):
    """Add a lap element to a TCX document"""

    # Only process laps with timestamps - this serves as a workaround for
    # extra fake/empty laps in FIT files from the Timex Run Trainer 2.0
    if lap.get_value('timestamp') is not None:

        lap_num = lap.get_value("message_index") + 1

        start_time = lap.get_value("start_time")
        end_time = lap.get_value("timestamp")
        totaltime = lap.get_value("total_elapsed_time")

        stored_distance = lap.get_value("total_distance")
        calculated_distance = sum_distance(activity, start_time, end_time)

        if fixed_distance is not None:
            reference_distance = fixed_distance
        else:
            reference_distance = calculated_distance

        try:
            lap_scaling_factor = reference_distance / stored_distance
        except ZeroDivisionError:
            lap_scaling_factor = 1.00
        if calibrate and per_lap_cal:
            scaling_factor = lap_scaling_factor
        else:
            scaling_factor = activity_scaling_factor

        max_speed = lap.get_value("max_speed")
        avg_speed = lap.get_value("avg_speed")

        calories = lap.get_value("total_calories")

        avg_heart = lap.get_value("avg_heart_rate")
        max_heart = lap.get_value("max_heart_rate")

        intensity = INTENSITY_MAP[lap.get_value("intensity")]

        avg_cadence = lap.get_value("avg_cadence")
        max_cadence = lap.get_value("max_cadence")

        if lap.get_value("lap_trigger"):
            triggermet = LAP_TRIGGER_MAP[lap.get_value("lap_trigger")]
        else:
            triggermet = LAP_TRIGGER_MAP["manual"]

        lapelem = create_sub_element(element, "Lap")
        lapelem.set("StartTime", iso_Z_format(start_time))


        #
        # TotalTimeSeconds
        #
        create_sub_element(lapelem, "TotalTimeSeconds", str("%d" % totaltime))


        #
        # DistanceMeters
        #
        lap_dist_elem = create_sub_element(lapelem,
                                           "DistanceMeters",
                                           str("%d" % stored_distance)
                                           )


        #
        # MaximumSpeed
        #
        lap_max_spd_elem = create_sub_element(lapelem,
                                              "MaximumSpeed",
                                              str("%.3f" % max_speed))


        #
        # Calories
        #
        create_sub_element(lapelem, "Calories", str("%d" % calories))


        #
        # AverageHeartRateBpm
        #
        if avg_heart is not None:
            heartrateelem = create_sub_element(lapelem, "AverageHeartRateBpm")
            heartrateelem.set(
                XML_SCHEMA + "type", "HeartRateInBeatsPerMinute_t")
            create_sub_element(heartrateelem, "Value", str("%d" % avg_heart))


        #
        # MaximumHeartRateBpm
        #
        if max_heart is not None:
            heartrateelem = create_sub_element(lapelem, "MaximumHeartRateBpm")
            heartrateelem.set(
                XML_SCHEMA + "type", "HeartRateInBeatsPerMinute_t")
            create_sub_element(heartrateelem, "Value", str("%d" % max_heart))


        #
        # Intensity
        #
        create_sub_element(lapelem, "Intensity", intensity)


        #
        # Cadence (bike)
        #
        if avg_speed or avg_cadence or max_cadence:
            if sport == "Biking" and avg_cadence is not None:
                # Average bike cadence is stored in main lap element,
                # not as an extension, unlike average running cadence (below)
                create_sub_element(lapelem, "Cadence", str("%d" % avg_cadence))


        #
        # TriggerMethod
        #
        create_sub_element(lapelem, "TriggerMethod", triggermet)

        if dist_recalc:
            distance_used = calculated_distance
        elif calibrate:
            if fixed_distance is not None:
                distance_used = fixed_distance
            else:
                distance_used = stored_distance * scaling_factor
        else:
            distance_used = stored_distance


        #
        # Track
        #
        trackelem = create_sub_element(lapelem, "Track")
        # First build tps array (using timestamp as the index)
        # in order to coalesce values at the same timepoint
        # under a single trackpoint element
        tps = {}
        fit_epoch = datetime(1989, 12, 31).replace(tzinfo=utc)
        for trackpoint in activity.get_messages('record'):
            tts = trackpoint.get_value("timestamp")
            tsi = int((tts - fit_epoch).total_seconds())
            if tps.get(tsi) is None:
                tps[tsi] = {
                    'timestamp':        tts,
                    'cadence':          None,
                    'distance':         None,
                    'position_lat':     None,
                    'position_long':    None,
                    'heart_rate':       None,
                    'altitude':         None,
                    'speed':            None}
            for var in ['cadence',
                        'distance',
                        'position_lat',
                        'position_long',
                        'heart_rate',
                        'altitude',
                        'speed']:
                if trackpoint.get_value(var) is not None:
                    tps[tsi][var] = trackpoint.get_value(var)

        # Iterate through all trackpoints to grab the first point before the
        # start of the lap, then delete points that are not part of the lap
        prev = None
        for timestamp in sorted(tps, reverse=True):
            tp = tps[timestamp]
            if tp['timestamp'] < start_time and prev is None:
                prev = copy.copy(tp)
            if tp['timestamp'] < start_time or tp['timestamp'] > end_time:
                del tps[timestamp]

        # Then process all trackpoints for this lap, recalculating speed &
        # distance from GPS and adjusting if requested, before adding element
        stored_avg_speed = copy.copy(avg_speed)
        stored_max_speed = copy.copy(max_speed)
        distance = 0.0
        max_speed = 0.0
        tp_speed = None
        for timestamp in sorted(tps):
            tp = tps[timestamp]
            trackpointelem = create_sub_element(trackelem, "Trackpoint")
            if prev is not None:
                if prev['distance'] is None:
                    prev['distance'] = 0
                try:
                    tp_timedelta = (tp['timestamp'] -
                                    prev['timestamp']).total_seconds()
                    gps_dist = GreatCircleDistance(
                        (tp['position_lat'],
                         tp['position_long']),
                        (prev['position_lat'],
                         prev['position_long'])
                    ).meters
                    gps_speed = (gps_dist / tp_timedelta)
                    # Fallback to existing distance/speed stream data
                    # if the GPS data looks erroneous (acceleration test)
                    if (gps_speed / tp_timedelta) > MAX_ACCELERATION:
                        gps_speed = tp['speed']
                        gps_dist = tp['distance'] - prev['distance']
                except:
                    gps_speed = tp['speed']
                    gps_dist = tp['distance'] - prev['distance']

                if dist_recalc:
                    tp_dist = gps_dist
                elif calibrate:
                    tp_dist = (
                        tp['distance'] - prev['distance']) * scaling_factor
                else:
                    tp_dist = tp['distance'] - prev['distance']

                try:
                    if speed_recalc:
                        tp_speed = gps_speed
                    elif calibrate:
                        tp_speed = tp['speed'] * scaling_factor
                    else:
                        tp_speed = tp['speed']

                    total_cumulative_distance += tp_dist
                    distance += tp_dist
                    if tp_speed > max_speed:
                        max_speed = tp_speed

                except TypeError:
                    tp_speed = None

            # Store previous trackpoint before changing the current one
            prev = copy.copy(tp)

            # Adjust trackpoint distance & speed values if requested
            if ((dist_recalc or calibrate)
                    and tp['distance'] is not None
                    and total_cumulative_distance is not None):
                tp['distance'] = "{:.1f}".format(total_cumulative_distance)
            if ((speed_recalc or calibrate)
                    and tp['speed'] is not None
                    and tp_speed is not None):
                tp['speed'] = "{:.3f}".format(tp_speed)

            # Add trackpoint element
            add_trackpoint(trackpointelem, tp, sport)


        #
        # Notes
        #
        if fixed_distance is not None:
            precision_str = ("; known distance: {ref_dist:.3f} km "
                             "(FIT precision: {fit_precision:.1f}%; "
                             "GPS/footpod precision: {gps_precision:.1f}%)")
            reference = "known distance"
        else:
            precision_str = " (precision: {precision:.1f}%)"
            reference = "GPS/footpod"
        try:
            fit_precision_calc = (1 - (abs(reference_distance -
                                                  stored_distance) /
                                              reference_distance)) * 100
            gps_precision_calc = (1 - (abs(reference_distance -
                                                  calculated_distance) /
                                              reference_distance)) * 100
            precision_calc = (1 - (abs(calculated_distance -
                                                  stored_distance) /
                                              calculated_distance)) * 100
        except ZeroDivisionError:
            fit_precision_calc = 100
            gps_precision_calc = 100
            precision_calc = 100
        notes = ("Lap {lap_number:d}: {distance_used:.3f} km in {total_time!s}\n"
                 "Distance in FIT file: {fit_dist:.3f} km; "
                 "calculated via GPS/footpod: {gps_dist:.3f} km"
                 + precision_str + "\n"
                 "Footpod calibration factor setting: {old_cf:.1f}%; "
                 "new factor based on {reference} for this lap: {new_cf:.1f}%"
                 ).format(lap_number=lap_num,
                          distance_used=distance_used / 1000,
                          total_time=timedelta(seconds=int(totaltime)),
                          fit_dist=stored_distance / 1000,
                          gps_dist=calculated_distance / 1000,
                          ref_dist=reference_distance / 1000,
                          fit_precision=fit_precision_calc,
                          gps_precision=gps_precision_calc,
                          precision=precision_calc,
                          old_cf=current_cal_factor,
                          reference=reference,
                          new_cf=lap_scaling_factor * current_cal_factor)
        add_notes(lapelem, notes)


        #
        # Extensions (AvgSpeed, AvgRunCadence, MaxRunCadence, MaxBikeCadence)
        #
        if not all(var is None for var in (avg_speed, avg_cadence, max_cadence)):
            exelem = create_sub_element(lapelem, "Extensions")
            lx = create_sub_element(exelem, "LX")
            lx.set("xmlns",
                   "http://www.garmin.com/xmlschemas/ActivityExtension/v2")
            if avg_speed is not None:
                lap_avg_spd_elem = create_sub_element(lx,
                                                      "AvgSpeed",
                                                      str("%.3f" % avg_speed))
            if avg_cadence is not None and sport == "Running":
                create_sub_element(lx,
                                   "AvgRunCadence",
                                   str("%d" % avg_cadence))
            if max_cadence is not None:
                if sport == "Running":
                    create_sub_element(lx,
                                       "MaxRunCadence",
                                       str("%d" % max_cadence))
                elif sport == "Biking":
                    create_sub_element(lx,
                                       "MaxBikeCadence",
                                       str("%d" % max_cadence))

        # Adjust overall lap distance & speed values if required
        if calibrate:
            # Manual distance:
            if fixed_distance is not None:
                lap_dist_elem.text = "{:d}".format(int(fixed_distance))
                lap_avg_spd_elem.text = "{:.3f}".format(
                    fixed_distance / totaltime)
            else:
                lap_dist_elem.text = "{:d}".format(
                    int(stored_distance * scaling_factor))
                lap_avg_spd_elem.text = "{:.3f}".format(
                    stored_avg_speed * scaling_factor)
            lap_max_spd_elem.text = "{:.3f}".format(
                stored_max_speed * scaling_factor)
        # GPS recalculation options override calibration:
        if dist_recalc:
            lap_dist_elem.text = "{:d}".format(int(distance))
        if speed_recalc:
            lap_avg_spd_elem.text = "{:.3f}".format(distance / totaltime)
            lap_max_spd_elem.text = "{:.3f}".format(max_speed)

        return distance

    else:
        return 0


def add_activity(element,
                 session,
                 activity,
                 dist_recalc,
                 speed_recalc,
                 calibrate,
                 current_cal_factor,
                 per_lap_cal,
                 manual_lap_distance,
                 activity_scaling_factor):
    """Add an activity to a TCX document"""

    # Sport type
    sport = session.get_value("sport")
    sport_mapping = {"running": "Running", "cycling": "Biking"}
    sport = sport_mapping[sport] if sport in sport_mapping else "Other"

    actelem = create_sub_element(element, "Activity")
    actelem.set("Sport", sport)
    create_sub_element(actelem,
                       "Id",
                       iso_Z_format(session.get_value("start_time")))

    total_cumulative_distance = 0.0
    lap_num = 0
    for lap in activity.get_messages('lap'):
        if lap.get_value("start_time") == lap.get_value("timestamp"):
            continue    # skip very short laps that won't have any data
        if manual_lap_distance is not None:
            try:
                fixed_dist = manual_lap_distance[lap_num]
            except IndexError:
                fixed_dist = None
        else:
            fixed_dist = None
        lap_dist = add_lap(actelem,
                           activity,
                           lap,
                           sport,
                           dist_recalc,
                           speed_recalc,
                           calibrate,
                           current_cal_factor,
                           per_lap_cal,
                           fixed_dist,
                           activity_scaling_factor,
                           total_cumulative_distance)
        total_cumulative_distance += lap_dist
        lap_num += 1

    return (actelem, total_cumulative_distance)


def convert(filename,
            time_zone="auto",
            dist_recalc=False,
            speed_recalc=False,
            calibrate=False,
            per_lap_cal=False,
            manual_lap_distance=None,
            current_cal_factor=100.0):
    """Convert a FIT file to TCX format"""

    # Calibration requires either GPS recalculation or manual lap distance(s):
    if calibrate and not dist_recalc and manual_lap_distance is None:
        sys.stderr.write("Calibration requested, enabling distance recalculation from GPS/footpod.\n")
        dist_recalc = True

    # Calibration with manual lap distances implies
    # per-lap calibration:
    if calibrate and manual_lap_distance is not None:
        per_lap_cal = True

    document = create_document()
    element = create_sub_element(document.getroot(), "Activities")

    try:
        
        if time_zone == "auto":
            # We need activity object to be able to get trackpoints,
            # before re-creating activity again with timezone info
            activity = FitFile(filename,
                            check_crc=False,
                            data_processor=MyDataProcessor())
            activity.parse()
            lat = None
            lon = None
            for trackpoint in activity.get_messages('record'):
                if lat is not None and lon is not None:
                    break
                lat = trackpoint.get_value("position_lat")
                lon = trackpoint.get_value("position_long")
            if lat is not None and lon is not None:
                activity = FitFile(filename,
                                   check_crc=False,
                                   data_processor=TZDataProcessor(lat=lat,
                                                                  lon=lon))
        else:
            activity = FitFile(filename,
                               check_crc=False,
                               data_processor=TZDataProcessor(tzname=time_zone))
        activity.parse()

        session = next(activity.get_messages('session'))
        total_activity_distance = session.get_value('total_distance')
        total_calculated_distance = sum_distance(activity)
        activity_scaling_factor = (total_calculated_distance /
                                   total_activity_distance)
        new_cal_factor = activity_scaling_factor * current_cal_factor

        actelem, total_distance = add_activity(element,
                                               session,
                                               activity,
                                               dist_recalc,
                                               speed_recalc,
                                               calibrate,
                                               current_cal_factor,
                                               per_lap_cal,
                                               manual_lap_distance,
                                               activity_scaling_factor)
    except FitParseError as e:
        sys.stderr.write(str("Error while parsing .FIT file: %s" % e) + "\n")
        sys.exit(1)

    if dist_recalc:
        distance_used = total_calculated_distance
    elif calibrate:
        distance_used = total_distance
    else:
        distance_used = total_activity_distance

    method = ""
    if dist_recalc or speed_recalc or calibrate:
        parts = []

        if calibrate:
            if per_lap_cal:
                parts.append("calibration applied per lap")
            else:
                parts.append("calibration applied")
        if dist_recalc and speed_recalc:
            parts.append("speed and distance recalculated")
        elif dist_recalc:
            parts.append("distance recalculated")
        elif speed_recalc:
            parts.append("speed recalculated")

        if calibrate and manual_lap_distance is not None:
            reference = " from known distance (with GPS fill-in)"
        elif dist_recalc or speed_recalc:
            reference = " from GPS/footpod"

        method = "(" + ", ".join(parts) + reference + ")"

    notes = ("{total_laps:d} laps: {distance_used:.3f} km in {total_time!s} {dist_method:s}\n"
             "Distance in FIT file: {fit_dist:.3f} km; "
             "calculated via GPS/footpod: {gps_dist:.3f} km "
             "(precision: {precision:.1f}%)\n"
             "Footpod calibration factor setting: {old_cf:.1f}%; "
             "new factor based on recomputed distance: {new_cf:.1f}%"
             ).format(total_laps=session.get_value('num_laps'),
                      distance_used=distance_used / 1000,
                      total_time=timedelta(seconds=int(session.get_value(
                          'total_timer_time'))),
                      fit_dist=total_activity_distance / 1000,
                      gps_dist=total_calculated_distance / 1000,
                      precision=(1 - (abs(total_calculated_distance -
                                          total_activity_distance) /
                                      total_calculated_distance)) * 100,
                      old_cf=current_cal_factor,
                      new_cf=new_cal_factor,
                      dist_method=method)
    add_notes(actelem, notes)
    try:
        dinfo = next(activity.get_messages('device_info'))
        manufacturer = dinfo.get_value('manufacturer').title().replace('_', ' ')
        product_name = dinfo.get_value('descriptor').replace('_', ' ')
        product_id = dinfo.get_value('product')
        serial_number = dinfo.get_value('serial_number')
    except: # if no device_info message, StopIteration is thrown
        fid = next(activity.get_messages('file_id'))
        manufacturer = fid.get_value('manufacturer').title().replace('_', ' ')
        product_id = fid.get_value('product')
        product_name = PRODUCT_MAP[product_id] if product_id in PRODUCT_MAP else product_id
        serial_number = fid.get_value('serial_number')
    add_creator(actelem,
                manufacturer,
                product_name,
                product_id,
                serial_number
                )
    add_author(document)
    return document


def main():
    """Read arguments from command line to convert FIT file to TCX"""

    parser = argparse.ArgumentParser(prog="fit2tcx")

    parser.add_argument("FitFile", help="Input FIT file")
    parser.add_argument("TcxFile", help="Output TCX file")
    parser.add_argument(
        "-v",
        "--version",
        action='version',
        version='%(prog)s {version}'.format(version=__version__))
    parser.add_argument(
        "-z",
        "--timezone",
        action="store",
        type=str,
        default="auto",
        help="Specify the timezone for FIT file timestamps (default, 'auto', uses GPS data to lookup the local timezone)")
    parser.add_argument(
        "-d",
        "--recalculate-distance-from-gps",
        action="store_true",
        help="Recalculate distance from GPS data")
    parser.add_argument(
        "-s",
        "--recalculate-speed-from-gps",
        action="store_true",
        help="Recalculate speed from GPS data")
    parser.add_argument(
        "-c",
        "--calibrate-footpod",
        action="store_true",
        help="Use GPS-measured and/or known distance to calibrate footpod data")
    parser.add_argument(
        "-p",
        "--per-lap-calibration",
        action="store_true",
        help="Apply footpod calibration on a per lap basis")
    parser.add_argument(
        "-l",
        "--manual-lap-distance",
        action="append",
        default=None,
        type=float,
        help="Manually specify known lap distance(s) (in metres, use calibration to apply)")
    parser.add_argument(
        "-f",
        "--calibration-factor",
        action="store",
        default=100.0,
        type=float,
        help="Existing calibration factor (defaults to 100.0)")

    args = parser.parse_args()

    if (args.calibrate_footpod and
        not args.recalculate_distance_from_gps and
        not args.manual_lap_distance):
        parser.error("-c (--calibrate-footpod) requires either -d (--recalculate-distance-from-gps) or -l (--manual-lap-distance)")
        return 1

    try:
        document = convert(args.FitFile,
                           args.timezone,
                           args.recalculate_distance_from_gps,
                           args.recalculate_speed_from_gps,
                           args.calibrate_footpod,
                           args.per_lap_calibration,
                           args.manual_lap_distance,
                           args.calibration_factor)
        activity_notes = document.getroot().findtext(".//{*}Activity/{*}Notes")
        if activity_notes is not None:
            sys.stdout.write(str(activity_notes) + "\n")
        tcx = open(args.TcxFile, 'wb')
        tcx.write(lxml.etree.tostring(document.getroot(),
                                      pretty_print=True,
                                      xml_declaration=True,
                                      encoding="UTF-8"))
        return 0
    except FitParseError as exception:
        sys.stderr.write(str(exception) + "\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
