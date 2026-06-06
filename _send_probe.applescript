tell application "TouchDesigner" to activate
delay 0.5
tell application "System Events"
    tell process "TouchDesigner"
        keystroke "exec(open('/Users/thomasadair/projects/touchdesigner-dj-suite/touchdesigner/scripts/_probe_composite.py').read())"
        delay 0.2
        key code 36
    end tell
end tell
