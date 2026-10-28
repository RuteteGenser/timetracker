import QtQuick

// Shown after a timer stops: an optional note with an on-screen keyboard.
// Knob: turn moves the outline between Delete, Skip and Save; press activates it.
// Skip starts outlined, so a single press of the button dismisses the prompt.
// Delete throws the timer that was just stopped away (its time no longer counts); it needs
// two presses: the first turns it dark red and says Confirm.
Rectangle {
    id: root
    color: "#101216"

    property real u: height / 720
    property bool shift: true
    readonly property real gap: 12 * u   // space between keys, both ways
    readonly property var rows: ["1234567890", "qwertyuiop", "asdfghjkl'", "zxcvbnm,.-"]

    function span(s) {
        var m = Math.floor(s / 60), sec = s % 60
        if (s < 60) return s + "s"
        if (s < 3600) return m + "m " + (sec < 10 ? "0" : "") + sec + "s"
        return Math.floor(s / 3600) + "h " + (m % 60 < 10 ? "0" : "") + (m % 60) + "m"
    }

    onVisibleChanged: if (visible) shift = ctl.noteText.length === 0  // capital first letter of a new note

    // Swallow taps so nothing underneath reacts.
    MouseArea { anchors.fill: parent }

    Column {
        anchors { fill: parent; margins: 20 * root.u }
        spacing: root.gap

        Row {
            spacing: 16 * root.u
            Text {
                text: ctl.noteKind === "rename" ? "Rename" : "What did you do?"
                color: "#ffffff"; font.pixelSize: 38 * root.u; font.bold: true
            }
            Text {
                anchors.baseline: parent.children[0].baseline
                text: ctl.noteProject + "  ·  " + root.span(ctl.noteSeconds)
                color: "#aab2bf"; font.pixelSize: 28 * root.u
            }
        }

        Rectangle {   // the note so far
            width: parent.width; height: 84 * root.u
            radius: 14 * root.u; color: "#1f232b"
            Text {
                anchors { fill: parent; margins: 18 * root.u }
                verticalAlignment: Text.AlignVCenter
                text: ctl.noteText.length ? ctl.noteText + "▏" : "Optional note…"
                color: ctl.noteText.length ? "#ffffff" : "#6b7380"
                font.pixelSize: 34 * root.u
                elide: Text.ElideLeft
            }
        }

        Repeater {
            model: root.rows
            Row {
                id: keyRow
                property string chars: modelData
                spacing: root.gap
                Repeater {
                    model: keyRow.chars.length
                    KeyButton {
                        u: root.u
                        width: (root.width - 40 * root.u - 10 * root.gap) / 11
                        height: 76 * root.u
                        label: root.shift ? keyRow.chars[index].toUpperCase() : keyRow.chars[index]
                        onClicked: {
                            ctl.noteType(label)
                            root.shift = false
                        }
                    }
                }
                KeyButton {   // backspace ends the first row
                    visible: keyRow.chars === root.rows[0]
                    u: root.u
                    width: (root.width - 40 * root.u - 10 * root.gap) / 11
                    height: 76 * root.u
                    label: "⌫"
                    onClicked: ctl.noteBackspace()
                }
            }
        }

        Row {
            spacing: root.gap
            KeyButton {
                u: root.u; width: 130 * root.u; height: 76 * root.u
                label: "Shift"; color: root.shift ? "#4a5160" : "#2a2f39"
                onClicked: root.shift = !root.shift
            }
            KeyButton {
                property int buttons: ctl.noteKind === "rename" ? 2 : 3   // Delete only exists for notes
                u: root.u; width: root.width - 40 * root.u - (buttons + 1) * root.gap - 130 * root.u - buttons * 170 * root.u
                height: 76 * root.u; label: "space"
                onClicked: ctl.noteType(" ")
            }
            KeyButton {
                u: root.u; width: 170 * root.u; height: 76 * root.u
                visible: ctl.noteKind === "note"
                label: ctl.noteDeleteArmed ? "Confirm" : "Delete"; danger: true
                armed: ctl.noteDeleteArmed; focused: ctl.noteFocus === 0
                onClicked: ctl.noteDelete()
            }
            KeyButton {
                u: root.u; width: 170 * root.u; height: 76 * root.u
                label: ctl.noteKind === "rename" ? "Cancel" : "Skip"; focused: ctl.noteFocus === 1
                onClicked: ctl.noteSkip()
            }
            KeyButton {
                u: root.u; width: 170 * root.u; height: 76 * root.u
                label: "Save"; accent: true; focused: ctl.noteFocus === 2
                onClicked: ctl.noteSave()
            }
        }
    }
}
