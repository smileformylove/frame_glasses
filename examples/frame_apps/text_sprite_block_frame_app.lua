local data = require('data.min')
local text_sprite_block = require('text_sprite_block.min')

local MSG_CODE = 0x20

data.parsers[MSG_CODE] = text_sprite_block.parse_text_sprite_block

print('unicode_text_ready')

while true do
    if data.process_raw_items() > 0 then
        local block = data.app_data[MSG_CODE]
        if block ~= nil and block.first_sprite_index > 0 then
            local line_index = 1
            for i = block.first_sprite_index, block.last_sprite_index do
                local sprite = block.sprites[i]
                local offset = block.offsets[line_index]
                if sprite ~= nil then
                    local x = 1
                    local y = 1
                    if offset ~= nil then
                        x = offset.x + 1
                        y = offset.y + 1
                    end
                    frame.display.bitmap(x, y, sprite.width, 2 ^ sprite.bpp, 0, sprite.pixel_data)
                end
                line_index = line_index + 1
            end
            frame.display.show()
        end
    end
    frame.sleep(0.02)
end
