-- postresolve runs after the packet has been answered, and can be used to change things
-- or still drop
local websocket = require "http.websocket"
local ws = websocket.new_from_uri("ws://127.0.0.1:8765")
ws:connect()

function postresolve(dq)
    pdnslog("postresolve called for " .. dq.qname:toString())
    local records = dq:getRecords()
    for k, v in pairs(records) do
        pdnslog(k .. " " .. v.name:toString() .. " " .. v:getContent() .. " " .. v.type)
        local message = ""
        pdnslog(k .. " " .. v.name:toString() .. " " .. v:getContent() .. " " .. v.type)
        if v.type == pdns.A then
            message = v.name:toString() .. ":A:" .. v:getContent()
        end
        if v.type == pdns.CNAME then
            message = v.name:toString() .. ":CNAME:" .. v:getContent()
        end
        if string.len(message) > 0 then
            pdnslog(message)
            if not ws:send(message) then
                pdnslog('Reconnecting ipt-server')
                ws = nil
                ws = websocket.new_from_uri("ws://127.0.0.1:8765")
                ws:connect()
            end
        end
    end
    dq:setRecords(records)
    return true
end
function maintenance()
    local x =ws:receive(0)
    if not x == nil then
        pdnslog(x)
    end
end