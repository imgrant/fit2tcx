# fit2tcx
Convert a FIT file to TCX format, designed for use with Timex Run Trainer 2.0

The script preserves lap structure, and has options for recalculating/recalibrating stored speed and distance data from the GPS track in the case where a footpod was used.

## Notes
The -t/--local-timezone option is aimed at the Timex Run Trainer 2.0, which stores the time in local time format, rather than UTC. It will look up the coordinates of the start of the run and work out what the time difference from UTC is.

For manual specification of lap distances, use multiple -l/--manual-lap-distance flags and values, in the order of the laps in the file, as appropriate.
