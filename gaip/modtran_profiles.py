#!/usr/bin/env python


MIDLAT_SUMMER_ALBEDO = """TM  2    2    2    1    2    2    2    2    2    2    1    1    0  10.000{albedo:7.2f}
TFF  8   0   375.000  g{water:7.5f}    a{ozone:5.3f}     T f f          t      0.3         0      0.70         0         0
DATA/{filter_function:<75}
    1    0    0    0    0    0{visibility:10.3f}     0.000     0.000     0.000{elevation:10.3f}
{sat_height:10.3f}{elevation:10.3f}{sat_view:10.3f}     0.000     0.000     0.000    0          0.000
    1    0{doy:5d}    0
{lat:10.3f}{lon:10.3f}     0.000     0.000{time:10.3f}{sat_azimuth:10.3f}     0.000     0.667
     350.0    2600.0       1.0       1.0RN#       NT    T
    0
"""

TROPICAL_ALBEDO = """TM  1    2    2    1    1    1    1    1    1    1    1    1    0  10.000{albedo:7.2f}
TFF  8   0   375.000  g{water:7.5f}    a{ozone:5.3f}     T f f          t      0.3         0      0.70         0         0
DATA/{filter_function:<75}
    1    0    0    0    0    0{visibility:10.3f}     0.000     0.000     0.000{elevation:10.3f}
{sat_height:10.3f}{elevation:10.3f}{sat_view:10.3f}     0.000     0.000     0.000    0          0.000
    1    0{doy:5d}    0
{lat:10.3f}{lon:10.3f}     0.000     0.000{time:10.3f}{sat_azimuth:10.3f}     0.000     0.667
     350.0    2600.0       1.0       1.0RN#       NT    T
    0
"""

MIDLAT_SUMMER_TRANSMITTANCE = """TM  2    2    2    1    2    2    2    2    2    2    1    1    0  10.000{albedo:7.2f}
TFF  8   0   375.000  g{water:7.5f}    a{ozone:5.3f}     T f f          t      0.3         0      0.70         0         0
DATA/{filter_function:<75}
    1    0    0    0    0    0{visibility:10.5f}     0.000     0.000     0.000{elevation:10.3f}
{sat_height:10.3f}{elevation:10.3f}{sat_view:10.3f}     0.000     0.000     0.000    0          0.000
    2    0{doy:5d}    0
     0.000{sat_view_offset:10.3f}                                                       0.667
     350.0    2600.0       1.0       1.0RN#       NT    T
    0
"""

TROPICAL_TRANSMITTANCE = """TM  1    2    2    1    1    1    1    1    1    1    1    1    0  10.000{albedo:7.2f}
TFF  8   0   375.000  g{water:7.5f}    a{ozone:5.3f}     T f f          t      0.3         0      0.70         0         0
DATA/{filter_function:<75}
    1    0    0    0    0    0{visibility:10.5f}     0.000     0.000     0.000{elevation:10.3f}
{sat_height:10.3f}{elevation:10.3f}{sat_view:10.3f}     0.000     0.000     0.000    0          0.000
    2    0{doy:5d}    0
     0.000{sat_view_offset:10.3f}                                                       0.667
     350.0    2600.0       1.0       1.0RN#       NT    T
    0
"""
