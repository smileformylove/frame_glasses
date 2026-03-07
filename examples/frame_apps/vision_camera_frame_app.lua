local data = require('data.min')
local camera = require('camera.min')

local CAPTURE_MSG_CODE = 0x0D

data.parsers[CAPTURE_MSG_CODE] = camera.parse_capture_settings

print('vision_camera_ready')

while true do
    if data.process_raw_items() > 0 then
        local settings = data.app_data[CAPTURE_MSG_CODE]
        if settings ~= nil then
            frame.display.text('capturing...', 1, 1)
            frame.display.show()
            camera.capture_and_send(settings)
            data.app_data[CAPTURE_MSG_CODE] = nil
            print('vision_capture_sent')
        end
    end
    frame.sleep(0.02)
end
