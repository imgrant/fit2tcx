#!/usr/bin/env python
#
# trt2import - copy & convert FIT files from a Timex Run Trainer 2.0
#
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

from __future__ import print_function, division
import sys
import os
import argparse
import string
import glob
import shutil
import struct
import time
import lxml.etree
import subprocess
import fit2tcx
import UploadGarmin

__prog__ = "trt2import"
__desc__ = "Timex Run Trainer 2.0 FIT file importer"
__version__ = "4.0"


def main():
    try:
        parser = argparse.ArgumentParser(prog=__prog__)
        parser.add_argument("drive", help="Drive letter for the watch USB device")
        parser.add_argument("folder", help="Root folder for storing copied/converted files")
        parser.add_argument(
            "-v", "--version", action='version',
            version='%(prog)s {version}'.format(version=__version__))
        parser.add_argument(
            "-o", "--overwrite",
            action="store_true", default=False, help="Force overwriting existing files (default: don't overwrite)")
        parser.add_argument(
            "-t", "--convert-to-tcx",
            action="store_true", default=False, help="Also convert to TCX")
        parser.add_argument(
            "-g", "--convert-to-gpx",
            action="store_true", default=False, help="Also convert to GPX (requires GPSBabel, implies -t)")
        parser.add_argument(
            "-u", "--upload-to-gc",
            action="store_true", default=False, help="Also upload the activity to Garmin Connect (uses TCX, implies -t)")
        parser.add_argument(
            "-n", "--username",
            action="store", help="Username for Garmin Connect")
        parser.add_argument(
            "-p", "--password",
            action="store", help="Password for Garmin Connect")
        parser.add_argument(
            "-d", "--recalculate-distance",
            action="store_true", default=False, help="Recalculate distance from GPS for TCX and GPX")
        parser.add_argument(
            "-s", "--recalculate-speed",
            action="store_true", default=False, help="Recalculate speed from GPS for TCX and GPX")
        parser.add_argument(
            "-c", "--calibrate-footpod",
            action="store_true", default=False, help="Use GPS-measured and/or known distance to calibrate footpod data for TCX and GPX")
        parser.add_argument(
            "-l", "--per-lap-calibration",
            action="store_true", default=False, help="Apply footpod calibration on a per lap basis for TCX and GPX (default: apply calibration per activity)")
        parser.add_argument(
            "-f", "--calibration-factor",
            action="store", default=-1, type=float,
            help="Override watch calibration factor (default: read current factor from watch)")
        args = parser.parse_args()

        # GPX conversion requires TCX, so make sure it's set if applicable:
        if args.convert_to_gpx:
            args.convert_to_tcx = True

        # Garmin Connect dependencies:
        if args.upload_to_gc:
            args.convert_to_tcx = True
            if args.username is None:
                print("Error: username for upload to Garmin Connect was not specified.")
                return 1
            if args.password is None:
                print("Error: password for upload to Garmin Connect was not specified.")
                return 1

    except Exception as e:
        print(e)
        return 1

    else:

        # Check the drive for ACTIVITY folder and FIT files
        DRIVE_LETTER = args.drive[:1]
        if not os.path.exists(DRIVE_LETTER + ":\\ACTIVITY"):
            print("No ACTIVITY folder found - is drive "+DRIVE_LETTER+" a Timex Run Trainer 2.0?")
            return 1

        fitFiles = glob.glob(DRIVE_LETTER + ":\\ACTIVITY\\*\\*.FIT")
        numFitFiles = len(fitFiles)
        if not numFitFiles >= 1:
            print("No activities found")
            return
        else:
            if numFitFiles == 1:
                noun = "activity"
            else:
                noun = "activities"
            print(str(numFitFiles)+" "+noun+" found")

        # Use supplied calibration factor
        if args.calibration_factor > -1:
            watch_cal_factor = args.calibration_factor
        else:
        # Get the current calibration factor from the watch
            try:
                settings = open(DRIVE_LETTER + ":\\SETTINGS\\M255-1.SET", mode="rb").read()
                watch_cal_factor = struct.unpack("h", settings[4:6])[0] / 10
                print("Calibration factor read from watch: "
                      "{cf:.1f}%".format(cf=watch_cal_factor))
            except:
                print("Unable to read calibration factor, "
                      "defaulting to 100.0%")
                watch_cal_factor = 100.0

        if args.upload_to_gc:
            # Create GC upload object
            gc = UploadGarmin.UploadGarmin()
            
            # LOGIN
            if not gc.login(args.username, args.password):
              print("Garmin Connect login failed - please verify your login credentials")
              return 1
            else:
              print("Garmin Connect login successful for user {user!s}".format(user=args.username))

        numImported = 0
        overallReturnCode = 0

        # Process FIT files on watch
        for srcFit in fitFiles:
            (letter, activity, date, filename) = srcFit.split("\\")
            year    = date[0:4]
            month   = date[4:6]
            day     = date[6:8]
            hourmin = filename[0:4]
            basename = "-".join([year, month, day]) + "_" + hourmin

            dstYearFolder = args.folder + "\\" + year
            dstFitFolder = dstYearFolder + "\\" + "FIT"
            dstTcxFolder = dstYearFolder + "\\" + "TCX"
            dstGpxFolder = dstYearFolder + "\\" + "GPX"

            # Create destination folders if needed:
            if not os.path.exists(dstFitFolder):
                os.makedirs(dstFitFolder)
            if not os.path.exists(dstTcxFolder) and args.convert_to_tcx:
                os.makedirs(dstTcxFolder)
            if not os.path.exists(dstGpxFolder) and args.convert_to_gpx:
                os.makedirs(dstGpxFolder)

            dstFit  = dstFitFolder + "\\" + basename + ".FIT"
            dstTcx  = dstTcxFolder + "\\" + basename + ".tcx"
            dstGpx  = dstGpxFolder + "\\" + basename + ".gpx"

            print()

            if os.path.exists(dstFit) and not args.overwrite:
                print("FIT file '{file!s}' has already been imported, skipping".format(
                    file=os.path.basename(srcFit)))
            else:

                # Copy the FIT file
                try:
                    shutil.copy2(srcFit, dstFit)
                    numImported += 1
                    print("FIT file '{file!s}' copied to {path!s}".format(
                        file=os.path.basename(srcFit),
                        path=dstFit))
                except IOError as e:
                    print("Error: unable to copy FIT file '{file!s}'. ({err!s})".format(
                        file=os.path.basename(srcFit),
                        err=e))
                    overallReturnCode = 1

                # Convert to TCX
                if args.convert_to_tcx:
                    try:
                        document = fit2tcx.convert(srcFit,
                                                   tz_is_local=True,
                                                   dist_recalc=args.recalculate_distance,
                                                   speed_recalc=args.recalculate_speed,
                                                   calibrate=args.calibrate_footpod,
                                                   per_lap_cal=args.per_lap_calibration,
                                                   manual_lap_distance=None,
                                                   current_cal_factor=watch_cal_factor)
                        tcxFile = open(dstTcx, 'wb')
                        tcxFile.write(lxml.etree.tostring(
                            document.getroot(),
                            pretty_print=True,
                            xml_declaration=True,
                            encoding="UTF-8")
                        )
                        tcxFile.close()
                        print("Converted TCX file saved to {path!s}".format(path=dstTcx))
                    except Exception as e:
                        print("Error: unable to convert FIT file '{file!s}' to TCX. ({err!s})".format(
                            file=os.path.basename(srcFit),
                            err=e))
                        overallReturnCode = 1

                # Convert to GPX (via external call to GPSBabel)
                if args.convert_to_gpx:
                    try:
                        subprocess.call(["gpsbabel",
                                         "-i", "gtrnctr",
                                         "-f", dstTcx,
                                         "-o", "gpx,gpxver=1.1,garminextensions=1",
                                         "-F", dstGpx],
                                         shell=True)
                        print("Converted GPX file saved to {path!s}".format(path=dstGpx))
                    except Exception as e:
                        print("Error: unable to convert TCX file '{file!s}' to GPX. ({err!s})".format(file=os.path.basename(dstTcx), err=e))
                        overallReturnCode = 1

                # Upload to Garmin Connect
                if args.upload_to_gc:
                    try:
                        status, id_msg = gc.upload_file(dstTcx)
                        if status == 'SUCCESS':
                            print("TCX file successfully uploaded to Garmin Connect. (ID: {id!s})".format(id=id_msg))
                        elif status == 'EXISTS':
                            print("TCX file not uploaded to Garmin Connect, a matching activity already exists. (ID: {id!s})".format(id=id_msg))
                        elif status == 'FAIL':
                            raise Exception(id_msg)
                    except Exception as e:
                        print("Error: unable to upload TCX file to Garmin Connect. ({err!s})".format(err=e))
                        overallReturnCode = 1

        if numImported == 1:
            iNoun = "activity"
        else:
            iNoun = "activities"
        print("\nAll done! "+str(numFitFiles)+" "+noun+" processed, "+str(numImported)+" new "+iNoun+" imported.")

        return overallReturnCode


if __name__ == "__main__":
    res = main()
    if res != 0:
        print("Some errors were encountered. See above for details.")
    input("\nPress Enter to exit ...")
    sys.exit(res)
    
