#!/usr/bin/env bash

curl -X GET "http://localhost:8000/status/benchmark" \
     -H "Authorization: Bearer $TOKEN"
