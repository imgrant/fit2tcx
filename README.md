# fit2tcx
Convert a FIT file to TCX format

fit2tcx is largely based on [FIT-to-TCX](https://github.com/Tigge/FIT-to-TCX) by Gustav Tiger and is ostensibly designed for use with Timex Run Trainer 2.0.

Lap structure is preserved, and additional options have been added for recalculating/recalibrating stored speed and distance data from the GPS track in the case where a footpod was used.

## Notes
The `-t` or `--local-timezone` option is aimed at the Timex Run Trainer 2.0, which stores the time in local time format, rather than UTC. It will look up the coordinates of the start of the run and work out what the time difference from UTC is.

For manual specification of lap distances, use multiple `-l` or `--manual-lap-distance` parameters, in the order of the laps in the file, as appropriate.
