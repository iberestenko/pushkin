#!/usr/bin/env bash

curl -X POST "http://localhost:8000/push?job_id=benchmark" \
     -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJhZG1pbiIsImV4cCI6MTc3ODEwNDc5MX0.TUDcOgCFpJrGvMm_ILUcZt1-W1C9a6-yRJxwUZ3dcB0" \
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

