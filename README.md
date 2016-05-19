# fit2tcx
Convert a FIT file to TCX format

fit2tcx is largely based on [FIT-to-TCX](https://github.com/Tigge/FIT-to-TCX) by Gustav Tiger and is ostensibly designed for use with the Timex Run Trainer 2.0, which produces slightly broken FIT files that cannot be uploaded to some services (e.g. Garmin Connect) or do not work correctly with others (e.g. Strava ignores lap data, Training Peaks shows 100 laps).

fit2tcx aims to be the most complete FTI to TCX converter for this situation; it preserves lap structure, cadence and heart rate data, and produces fully compliant TCX files that can be uploaded to Garmin Connect, Strava, etc.

Additional functions are provided for recalculating/recalibrating stored speed and distance data from the GPS track in the case where a footpod was used, or manually specifying known distances and rescaling the data accordingly.


## Requirements
The following python modules are required by fit2tcx:
* [lxml](http://lxml.de/)
* [pytz](http://pytz.sourceforge.net/)
* [tzwhere](https://pypi.python.org/pypi/tzwhere/)
* [geopy](https://github.com/geopy/geopy)
* [fitparse](http://dtcooper.github.io/python-fitparse/) - recommended is either [dtcooper/python-fitparse](https://github.com/dtcooper/python-fitparse) ('ng' branch), for python 2.5, or [kropp/python-fitparse](https://github.com/kropp/python-fitparse) ('python3' branch), for python 3.

The first four should be readily available via easy_install or pip. The version of fitparse available via pip might be out of date.


## Summary
    usage: fit2tcx [-h] [-v] [-t] [-d] [-s] [-c] [-p] [-l MANUAL_LAP_DISTANCE]
                   [-f CALIBRATION_FACTOR]
                   FitFile TcxFile

    positional arguments:
      FitFile               Input FIT file
      TcxFile               Output TCX file

    optional arguments:
      -h, --help            show this help message and exit
      -v, --version         show program's version number and exit
      -z, --timezone        Specify the timezone for FIT file timestamps
                            (default is to lookup the local timezone from the
                            GPS data)
      -d, --recalculate-distance-from-gps
                            Recalculate distance from GPS data
      -s, --recalculate-speed-from-gps
                            Recalculate speed from GPS data
      -c, --calibrate-footpod
                            Use GPS-measured and/or known distance to
                            calibrate footpod data
      -p, --per-lap-calibration
                            Apply footpod calibration on a per lap basis
      -l MANUAL_LAP_DISTANCE, --manual-lap-distance MANUAL_LAP_DISTANCE
                            Manually specify known lap distance(s) (in
                            metres, use calibration to apply)
      -f CALIBRATION_FACTOR, --calibration-factor CALIBRATION_FACTOR
                            Existing calibration factor (defaults to 100.0)


## Options
* `--timezone`
 Use this option with the Timex Run Trainer 2.0, which incorrectly stores the time in the FIT file in the local timezone, rather than UTC (as mandated by the FIT specification). By default (or if set to 'auto'), it converts the time to UTC by determining which local timezone applies to the activity based on the starting coordinates. For, e.g., a treadmill activity without GPS data, you can manually specify the timezone name, such as 'Europe/London'.

* `--recalculate-distance-from-gps`
This option recalculates the cumulative distance stream in the TCX file from the GPS data. Use this if you recorded distance from a footpod and wish to use the GPS data instead; if you used GPS to record the distance, there will be no (or little) difference.

* `--recalculate-speed-from-gps`
Similar to the previous option, this recalculates the speed data stream in the TCX file from the GPS data (i.e. by dividing the distance between trackpoints by the time elapsed). Use this if you recorded pace from a footpod and wish to use the GPS data instead.

* `--calibrate-footpod`
Use this option if the activity was recorded with a footpod and you wish to retrospectively calibrate it, based on the GPS data or manual distance (see below). If enabled, the distance and speed for each trackpoint will be scaled by a computed factor such that the total distance equals that calculated from GPS (or manually specified).

* `--per-lap-calibration`
In conjunction with the calibrate option (above), this option calculates a separate scaling factor for each lap in the activity, rather than a single factor for the whole activity.

* `--manual-lap-distance MANUAL_LAP_DISTANCE` (in metres)
Use this option when you know the actual distance of the activity (e.g. an athletics track). Scaling factors for calibration will then be based on this number, rather than that from GPS.
Specify the argument multiple times, once for each lap, in the order that laps were recorded, as appropriate (e.g. `-l 400 -l 800 -l 1609` for three laps, of 400 m, 800 m, and 1 mile). If you specify fewer distances than laps in the FIT file, subsequent laps will use the GPS-determined distance.

* `--calibration-factor`
Specify the calibration factor that was set on the watch when the activity was recorded (assumes 100.0% by default).


## Notes
The `-c (--calibrate-footpod)` option can be used with the `-d (--recalculate-distance-from-gps)` option to produce a file where the distance is determined by GPS, but the pace comes from the (auto-calibrated) footpod data; this is useful when you want to run with the footpod for instance pace, but use GPS for distance (albeit an after-the-fact computation).

Note that even if the `-d` or `-c` arguments are not given, information about GPS-recorded distance and footpod accuracy is recorded in the notes for each lap and the activity overall (the values are, of course, not used to change the actual data in the TCX file in the arguments aren't given), allowing you to compare. In the event that the FIT file was recorded using GPS data, the values will be the same and the footpod accuracy will be 100.0% (i.e. fit2tcx assumes that the distance reported by the FIT file comes from a footpod).


*******************************************************************************


# trt2import
trt2import is a companion program that leverages fit2tcx (and optionally, [GPSBabel](http://www.gpsbabel.org/)) to aid in copying and converting FIT files from a Timex Run Trainer 2.0.


## Requirements
The following python modules are required by trt2import:
* fit2tcx and associated requirements (see above)
* [UploadGarmin](http://sourceforge.net/projects/gcpuploader/) - available via pip as 'GcpUploader'


## Summary
    usage: trt2import [-h] [-v] [-o] [-t] [-g] [-u] [-n USERNAME] [-p PASSWORD]
                      [-d] [-s] [-c] [-l] [-f CALIBRATION_FACTOR]
                      drive folder

    positional arguments:
      drive                 Drive or root path to the watch USB device
      folder                Root folder for storing copied/converted files

    optional arguments:
      -h, --help            show this help message and exit
      -v, --version         show program's version number and exit
      -o, --overwrite       Force overwriting existing file
                            (default: don't overwrite)
      -t, --convert-to-tcx  Also convert to TCX
      -g, --convert-to-gpx  Also convert to GPX (requires GPSBabel, implies -t)
      -u, --upload-to-gc    Also upload the activity to Garmin Connect (uses TCX,
                            implies -t)
      -n USERNAME, --username USERNAME
                            Username for Garmin Connect
      -w PASSWORD, --password PASSWORD
                            Password for Garmin Connect
      -d, --recalculate-distance
                            Recalculate distance from GPS for TCX and GPX
      -s, --recalculate-speed
                            Recalculate speed from GPS for TCX and GPX
      -c, --calibrate-footpod
                            Use GPS-measured and/or known distance to calibrate
                            footpod data for TCX and GPX
      -p, --per-lap-calibration
                            Apply footpod calibration on a per lap basis for TCX
                            and GPX (default: apply calibration per activity)
      -f CALIBRATION_FACTOR, --calibration-factor CALIBRATION_FACTOR
                            Override watch calibration factor
                            (default: read current factor from watch)
      -z TIMEZONE, --timezone TIMEZONE
                            Override timezone detection
                            (default: lookup the local timezone from GPS data)


## Options
* `drive` can be a Windows drive letter such as `E:\` or a *nix mount point such as `/media/usb` representing the Timex Run Trainer 2.0 USB device.

* `folder` is where the FIT files will be copied to. Files will be renamed according to the date of the activity, and a folder hierarchy will be created inside the given folder for years (when the FIT file was created) and file type, e.g. `<folder>/2015/FIT/2015-11-28_1430.fit`

* `--overwrite`
If a file already exists at the target destination for a given FIT file on the watch, it won't be imported. Use this option to override that and copy regardless of existing files.

* `--convert-to-tcx`  Also convert the FIT file to TCX, stored at `<folder>/<year>/TCX/<filename>.tcx`

* `--convert-to-gpx`  Also convert to GPX (stored at `<folder>/<year>/GPX/<filename>.gpx`). This requires [GPSBabel](http://www.gpsbabel.org/) to be installed and available on %PATH%/$PATH. The GPX is produced from the TCX, so this option also implies `-t` above.

* `--upload-to-gc`  Also upload the activity to Garmin Connect. This uses the converted TCX file and so implies `-t` (above). Specify the username and password for the Garmin Connect account with the `-n` and `-w` options.

* `--recalculate-distance` See fit2tcx (above) - only applies to TCX and GPX conversion

* `--recalculate-speed` See fit2tcx (above) - only applies to TCX and GPX conversion

* `--calibrate-footpod` See fit2tcx (above) - only applies to TCX and GPX conversion

* `--per-lap-calibration` See fit2tcx (above) - only applies to TCX and GPX conversion

* `--calibration-factor CALIBRATION_FACTOR` See fit2tcx (above) - only applies to TCX and GPX conversion

* `--timezone TIMEZONE` See fit2tcx (above)


## Notes
### Calibration factor
Options set for trt2import apply to the whole import operation, which might involve multiple FIT files. e.g. whether the footpod calibration factor is read from the watch or manually specified, it applies to all the FIT files imported at that time. If individual FIT files were recorded with different factors, this will therefore not be correct.

### Default Programs Editor
A useful application of trt2import is on Windows, in conjunction with [Default Programs Editor](http://www.defaultprogramseditor.com/), where an autoplay handler can be set up for use with unknown USB devices, enabling one-click import and conversion of FIT files and upload to Garmin Connect when the Timex Run Trainer 2.0 is connected to the PC.
