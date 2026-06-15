tell application "TouchDesigner" to activate
delay 0.4
tell application "System Events"
    tell process "TouchDesigner"
        keystroke "exec(open('/Users/thomasadair/projects/touchdesigner-dj-suite/touchdesigner/scripts/_fix_aura.py').read())"
        delay 0.25
        key code 36
    end tell
end tell
