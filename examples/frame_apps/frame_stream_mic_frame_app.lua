local data = require('data.min')
local audio = require('audio.min')
local text_sprite_block = require('text_sprite_block.min')

local UNICODE_TEXT_MSG_CODE = 0x20
local PLAIN_TEXT_MSG_CODE = 0x21

local function parse_plain_text(data_block, prev)
    _ = prev
    return data_block
end

local function render_plain_text(text)
    frame.display.text(text, 1, 1)
    frame.display.show()
end

local function render_text_sprite_block(block)
    if block == nil or block.first_sprite_index == 0 then
        return
    end

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

data.parsers[PLAIN_TEXT_MSG_CODE] = parse_plain_text
data.parsers[UNICODE_TEXT_MSG_CODE] = text_sprite_block.parse_text_sprite_block

audio.start()
print('frame_stream_mic_ready')

while true do
    if data.process_raw_items() > 0 then
        local plain_text = data.app_data[PLAIN_TEXT_MSG_CODE]
        if plain_text ~= nil then
            render_plain_text(plain_text)
            data.app_data[PLAIN_TEXT_MSG_CODE] = nil
        end

        local unicode_block = data.app_data[UNICODE_TEXT_MSG_CODE]
        if unicode_block ~= nil then
            render_text_sprite_block(unicode_block)
            data.app_data[UNICODE_TEXT_MSG_CODE] = nil
        end
    end

    audio.read_and_send_audio()
    frame.sleep(0.01)
end
