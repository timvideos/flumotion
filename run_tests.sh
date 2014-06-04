#!/bin/bash

filename=working-tests.txt
test_to_run=""

while read line
do
    tests_to_run+=flumotion.test.$line' '
done < $filename

trial -rselect $tests_to_run