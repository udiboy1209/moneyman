#!/bin/bash

appname=$1
if [ -z "$appname" ]
then
  appname="moneyman"
fi

gunicorn --reload --bind 0.0.0.0:5000 wsgi:${appname}_app
