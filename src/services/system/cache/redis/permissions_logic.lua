-- permission cache logic for redis distributed permission caching
--
-- Stored as:
-- permissions:<identifier> -> JSON string
--
-- The caller should json.loads(...) the result.

local key = KEYS[1]

local data = redis.call("GET", key)

if not data then
    return "NOT_FOUND"
end

return data