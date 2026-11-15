#!/bin/bash
# shot.sh NAME... -> png/NAME.png at board size
S=/tmp/claude-1000/-home-liang-Projects-D1-Max/ecced633-c546-490e-ade6-e46e90a431ed/scratchpad
mkdir -p $S/appgen/png
for n in "$@"; do f=$S/dcanvas/project/$n.dc.html
 W=$(grep -o '"width":[0-9]*' $f | head -1 | cut -d: -f2); H=$(grep -o '"height":[0-9]*' $f | head -1 | cut -d: -f2)
 node /home/liang/Projects/D1_Max/wt-redesign/design/console-v2/gen/preview.js $f $S/appgen/png/$n.png $W $H &
done; wait
