local counter = 0

print('visual_probe_ready')

while true do
    frame.display.text('FRAME CONNECTED', 1, 1)
    frame.display.text('VISUAL PROBE', 1, 40)
    frame.display.text('COUNT ' .. tostring(counter), 1, 80)
    frame.display.show()
    counter = counter + 1
    frame.sleep(1.0)
end
