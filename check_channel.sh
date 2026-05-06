#!/usr/bin/env bash

docker exec -it pushkin-redis_db-1 redis-cli PSUBSCRIBE "pushkin:stream:benchmark:*"
