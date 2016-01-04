#!/usr/bin/env python
#
# Copy & convert FIT files from Timex Run Trainer 2.0
#

from __future__ import print_function, division
import sys
import os
from win32api import *
from win32gui import *
import win32con
import time
import argparse
import string
import glob
import shutil
import struct
import lxml.etree
import subprocess
import fit2tcx

__prog__ = "trt2import"
__desc__ = "Timex Run Trainer 2.0 FIT file importer"
__version__ = "2.0"


class WindowsBalloonTip:
    def __init__(self, title, msg):
        message_map = { win32con.WM_DESTROY: self.OnDestroy, }
        # Register the Window class.
        wc = WNDCLASS()
        hinst = wc.hInstance = GetModuleHandle(None)
        wc.lpszClassName = "PythonTaskbar"
        wc.lpfnWndProc = message_map # could also specify a wndproc.
        classAtom = RegisterClass(wc)
        # Create the Window.
        style = win32con.WS_OVERLAPPED | win32con.WS_SYSMENU
        self.hwnd = CreateWindow( classAtom, "Taskbar", style, \
                0, 0, win32con.CW_USEDEFAULT, win32con.CW_USEDEFAULT, \
                0, 0, hinst, None)
        UpdateWindow(self.hwnd)
        # Icon management.
        iconPathName = os.path.abspath(os.path.join(sys.path[0], __prog__+".ico" ))
        icon_flags = win32con.LR_LOADFROMFILE | win32con.LR_DEFAULTSIZE
        try:
           hicon = LoadImage(hinst, iconPathName, \
                    win32con.IMAGE_ICON, 0, 0, icon_flags)
        except:
            # hicon = LoadIcon(0, win32con.IDI_APPLICATION)
            hicon = ExtractIcon(0, sys.executable, 0)
        flags = NIF_ICON | NIF_MESSAGE | NIF_TIP
        nid = (self.hwnd, 0, flags, win32con.WM_USER+20, hicon, "tooltip")
        # Notify
        Shell_NotifyIcon(NIM_ADD, nid)
        Shell_NotifyIcon(NIM_MODIFY, \
                         (self.hwnd, 0, NIF_INFO, win32con.WM_USER+20,\
                          hicon, "Balloon  tooltip",msg,200,title))
        # self.show_balloon(title, msg)
        time.sleep(4)
        # Destroy
        DestroyWindow(self.hwnd)
        classAtom = UnregisterClass(classAtom, hinst)

    def OnDestroy(self, hwnd, msg, wparam, lparam):
        nid = (self.hwnd, 0)
        Shell_NotifyIcon(NIM_DELETE, nid)
        PostQuitMessage(0) # Terminate the app.


class ToolTipOut():
    def __init__(self):
        pass
    def write(self, string):
        msg = string.strip()
        WindowsBalloonTip(__desc__, msg)
    def flush(self):
        pass


def main():
    if ( os.path.basename(sys.executable) == "pythonw.exe" or
    os.path.basename(sys.executable) == "trt2import.exe" ):
        sys.stdout = ToolTipOut()
        sys.stderr = ToolTipOut()
    try:
        parser = argparse.ArgumentParser(prog=__prog__)
        parser.add_argument("drive", help="Drive letter for the watch USB device")
        parser.add_argument("folder", help="Root folder for storing copied/converted files")
        parser.add_argument(
            "-v", "--version",action='version',
            version='%(prog)s {version}'.format(version=__version__))
        parser.add_argument(
            "-o", "--overwrite",
            action="store_true", default=False, help="Force overwriting existing files (default: don't overwrite)")
        parser.add_argument(
            "-t", "--convert_to_tcx",
            action="store_true", default=False, help="Also convert to TCX (default: don't convert to TCX)")
        parser.add_argument(
            "-g", "--convert_to_gpx",
            action="store_true", default=False, help="Also convert to GPX (requires GPSBabel, implies -t, default: don't convert to GPX)")
        parser.add_argument(
            "-d", "--recalculate-distance",
            action="store_true", default=False, help="Recalculate distance from GPS for TCX and GPX (default: don't recalculate)")
        parser.add_argument(
            "-s", "--recalculate-speed",
            action="store_true", default=False, help="Recalculate speed from GPS for TCX and GPX (default: don't recalculate)")
        parser.add_argument(
            "-c", "--calibrate-footpod",
            action="store_true", default=False, help="Use GPS-measured and/or known distance to calibrate footpod data for TCX and GPX (default: calibrate footpod)")
        parser.add_argument(
            "-p", "--per-lap-calibration",
            action="store_true", default=False, help="Apply footpod calibration on a per lap basis for TCX and GPX (default: apply calibration per activity)")
        parser.add_argument(
            "-f", "--calibration-factor",
            action="store", default=-1, type=float,
            help="Override watch calibration factor (default: read current factor from watch)")
        args = parser.parse_args()
        # GPX conversion requires TCX, so make sure it's set if applicable
        if args.convert_to_gpx:
            args.convert_to_tcx = True
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
        if not len(fitFiles) >= 1:
            print("No activities found")
            return

        # Use supplied calibration factor
        if args.calibration_factor > -1:
            watch_cal_factor = args.calibration_factor
        else:
        # Get the current calibration factor from the watch
            try:
                settings = open(DRIVE_LETTER + ":\\SETTINGS\\M255-1.SET", mode="rb").read()
                watch_cal_factor = struct.unpack("h", settings[4:6])[0] / 10
                print("Current calibration factor read from watch: "
                      "{cf:.1f}%".format(cf=watch_cal_factor))
            except:
                print("Unable to read current calibration factor, "
                      "defaulting to 100.0%")
                watch_cal_factor = 100.0

        # Process FIT files on watch
        for srcFit in fitFiles:
            (letter, activity, date, filename) = srcFit.split("\\")
            year    = date[0:4]
            month   = date[4:6]
            day     = date[6:8]
            time    = filename[0:4]
            basename = "-".join([year, month, day]) + "_" + time

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

            if os.path.exists(dstFit) and not args.overwrite:
                print("FIT file '{file!s}' has already been imported, skipping".format(
                    file=os.path.basename(srcFit)))
            else:

                # Copy the FIT file
                try:
                    shutil.copy2(srcFit, dstFit)
                    print("FIT file '{file!s}' copied to {path!s}".format(
                        file=os.path.basename(srcFit),
                        path=dstFitFolder))
                except IOError as e:
                    print("Unable to copy FIT file '{file!s}'. {err!s}".format(
                        file=os.path.basename(srcFit),
                        err=e))
                    return 1

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
                        print("Converted TCX file '{file!s}' saved to {path!s}".format(
                            file=os.path.basename(dstTcx),
                            path=dstTcxFolder))
                    except Exception as e:
                        print("Unable to convert FIT file '{file!s}' to TCX. {err!s}".format(
                            file=os.path.basename(srcFit),
                            err=e))
                        return 1

                # Convert to GPX (via external call to GPSBabel)
                if args.convert_to_gpx:
                    try:
                        subprocess.call(["gpsbabel",
                                         "-i", "gtrnctr",
                                         "-f", dstTcx,
                                         "-o", "gpx,gpxver=1.1,garminextensions=1",
                                         "-F", dstGpx],
                                         shell=True)
                        print("Converted GPX file '{file!s}' saved to {path!s}".format(
                            file=os.path.basename(dstGpx),
                            path=dstGpxFolder))
                    except Exception as e:
                        print("Unable to convert TCX file '{file!s}' to GPX. {err!s}".format(file=os.path.basename(dstTcx), err=e))
                        return 1

        print("All done!")
        return


if __name__ == "__main__":
    sys.exit(main())
