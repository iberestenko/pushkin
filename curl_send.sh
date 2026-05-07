#!/usr/bin/env bash

curl -X POST "http://localhost:8000/push?job_id=benchmark" \
     -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" \
     -d '[{
       "ip": "mock_switch",
       "port": 22,
       "user": "admin",
       "pw": "admin",
       "cmds": [
         "conf t",
         "interface Gi0/1",
         "description TEST_BY_PUSHKIN",
         "end",
         "show ip interface brief"
       ]
     }]'

