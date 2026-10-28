import QtQuick

// Set the date and time. Knob: turn moves the outline over Year, Month, Day, Hour, Minute,
// Cancel and Save; press a field to edit it (turn changes it, press again to finish).
// Touch: tap a field to edit it, or use the + and - buttons.
Rectangle {
    id: root
    color: "#101216"

    property real u: height / 720
    readonly property real pad: 15 * width / 1280
    readonly property real gap: 16 * u
    readonly property real colW: (width - 2 * pad - 4 * gap) / 5
    readonly property var labels: ["Year", "Month", "Day", "Hour", "Minute"]

    function text(i) {
        var v = ctl.dtFields[i]
        return i === 0 ? "" + v : (v < 10 ? "0" + v : "" + v)
    }

    Text {
        x: root.pad + 8 * root.u; y: root.pad
        height: 60 * root.u
        verticalAlignment: Text.AlignVCenter
        text: "Date & time"
        color: "#ffffff"
        font.pixelSize: 40 * root.u
        font.bold: true
    }

    Text {
        x: root.pad + 8 * root.u; y: root.pad + 62 * root.u
        width: root.width - 2 * root.pad
        text: ctl.dtError.length ? ctl.dtError : "Turn to move, press to change a field, then Save."
        color: ctl.dtError.length ? "#ff7b7b" : "#aab2bf"
        font.pixelSize: 26 * root.u
        elide: Text.ElideRight
    }

    Repeater {
        model: 5
        Item {
            id: col
            x: root.pad + index * (root.colW + root.gap)
            y: root.pad + 120 * root.u
            width: root.colW
            height: 400 * root.u

            Text {
                width: parent.width
                horizontalAlignment: Text.AlignHCenter
                text: root.labels[index]
                color: "#aab2bf"
                font.pixelSize: 26 * root.u
            }
            KeyButton {
                y: 40 * root.u; width: parent.width; height: 76 * root.u; u: root.u
                label: "+"
                onClicked: ctl.dtAdjust(index, 1)
            }
            Rectangle {
                id: valueBox
                y: 128 * root.u; width: parent.width; height: 150 * root.u
                radius: 4 * root.u
                color: ctl.dtFocus === index && ctl.dtEditing ? "#3274d1" : "#1f232b"
                Text {
                    anchors.centerIn: parent
                    text: root.text(index)
                    color: "#ffffff"
                    font.pixelSize: 64 * root.u
                    font.bold: true
                }
                Rectangle {   // the outline: the knob is on this field
                    visible: ctl.dtFocus === index
                    anchors.fill: parent
                    radius: parent.radius
                    color: "transparent"
                    border.color: "#ffffff"
                    border.width: 6 * root.u
                }
                MouseArea { anchors.fill: parent; onClicked: ctl.dtTap(index) }
            }
            KeyButton {
                y: 290 * root.u; width: parent.width; height: 76 * root.u; u: root.u
                label: "−"
                onClicked: ctl.dtAdjust(index, -1)
            }
        }
    }

    Row {
        x: root.pad; y: root.height - root.pad - 96 * root.u - 20 * root.u
        spacing: root.gap
        KeyButton {
            u: root.u; width: 260 * root.u; height: 84 * root.u
            label: "Cancel"; focused: ctl.dtFocus === 5
            onClicked: ctl.back()
        }
        KeyButton {
            u: root.u; width: 260 * root.u; height: 84 * root.u
            label: "Save"; accent: true; focused: ctl.dtFocus === 6
            onClicked: ctl.dtSave()
        }
    }
}
