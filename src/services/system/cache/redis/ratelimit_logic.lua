-- ratelimit logic for redis distributed rate limiting

-- Stored in redis as a hash with the following fields:
-- requests: number of requests made in the current window
-- limit: maximum number of requests allowed in the window
-- window: time window in seconds
-- last_request_time: timestamp of the last request made

local key = KEYS[1]
local current_time = tonumber(ARGV[1])
local too_soon_window = tonumber(ARGV[2]) -- Can be nil if not enforcing too soon

local data = redis.call(
    "HMGET",
    key,
    "requests",
    "limit",
    "window",
    "last_request_time"
)

local requests = tonumber(data[1])
local limit = tonumber(data[2])
local window = tonumber(data[3])
local last_request_time = tonumber(data[4])
local metadata = cjson.decode(data[5] or "{}") -- Assuming metadata is stored as a JSON string

-- Early return, the ratelimit must be set before. 
-- It is this way to enforce that the ratelimit is pulled straight from the database
-- after it either was deleted or not used in a long time.
-- This allows developers to invalidate a key when it is changed in any way and force an immediate update on the next request.
if not requests then
    return "NOT_FOUND"
end

if not limit or not window or not last_request_time then
    return "INVALID_DATA"
end

local time_elapsed = current_time - last_request_time

if too_soon_window and time_elapsed < too_soon_window then
    return "TOO_SOON"
end

if time_elapsed >= window then
    -- Reset the request count and update the last request time
    redis.call("HMSET", key, "requests", 1, "last_request_time", current_time)
    return "ALLOWED"
end

local refill_per_second = limit / window
local refill_amount = math.floor(time_elapsed * refill_per_second)

local new_requests = math.max(0, requests - refill_amount)

if new_requests + 1 > limit then
    return "DENIED"
else
    redis.call("HMSET", key, "requests", new_requests + 1, "last_request_time", current_time)
    return "ALLOWED"
end