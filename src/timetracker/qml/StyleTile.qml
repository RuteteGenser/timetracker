import QtQuick

// One card on the Style screen, split into four parts the knob visits in turn:
// colour (press: next colour), name (press: rename), time (press twice: reset today) and
// More (press: menu with Archive, Move left / right and Delete).
Item {
    id: root

    property string projectName
    property color tileColor
    property int today            // seconds worked today
    property int selectedPart: -1 // 0 colour, 1 name, 2 time, 3 more, -1 none
    property bool resetArmed      // time part waits for its confirming second press
    property real u: 1

    signal partTapped(int part)

    readonly property real gap: 16 * u
    readonly property real partWidth: width - 16 * u
    readonly property real usable: height - 16 * u - 3 * gap
    readonly property real partHeight: usable * 0.2933   // colour, name and time
    readonly property real moreHeight: usable * 0.12

    function pad(n) { return n < 10 ? "0" + n : "" + n }
    function span(s) {
        if (s < 3600)
            return Math.floor(s / 60) + "m " + pad(s % 60) + "s"
        return Math.floor(s / 3600) + "h " + pad(Math.floor(s / 60) % 60) + "m"
    }

    Rectangle {   // part 0: the colour itself
        id: colorPart
        x: 8 * root.u; y: 8 * root.u
        width: root.partWidth; height: root.partHeight
        radius: 20 * root.u
        color: root.tileColor
        Text {
            anchors { left: parent.left; bottom: parent.bottom; margins: 20 * root.u }
            text: "Color"
            color: "#ffffff"
            font.pixelSize: 25 * root.u
            font.bold: true
        }
        MouseArea { anchors.fill: parent; onClicked: root.partTapped(0) }
    }

    Rectangle {   // part 1: the name
        id: namePart
        x: 8 * root.u; y: colorPart.y + root.partHeight + root.gap
        width: root.partWidth; height: root.partHeight
        radius: 20 * root.u
        color: "#1f232b"
        Text {
            anchors { left: parent.left; right: parent.right; top: parent.top; margins: 20 * root.u }
            text: root.projectName
            color: "#ffffff"
            font.pixelSize: 34 * root.u
            font.bold: true
            height: parent.height - 100 * root.u   // leaves room for the "Rename" caption
            wrapMode: Text.WordWrap
            fontSizeMode: Text.Fit    // a long name gets smaller until it fits the part
            minimumPixelSize: 12 * root.u
            verticalAlignment: Text.AlignTop
        }
        Text {
            anchors { left: parent.left; bottom: parent.bottom; margins: 20 * root.u }
            text: "Rename"
            color: "#aab2bf"
            font.pixelSize: 25 * root.u
        }
        MouseArea { anchors.fill: parent; onClicked: root.partTapped(1) }
    }

    Rectangle {   // part 2: today's total, with reset
        id: timePart
        x: 8 * root.u; y: namePart.y + root.partHeight + root.gap
        width: root.partWidth; height: root.partHeight
        radius: 20 * root.u
        color: root.resetArmed ? "#e0701a" : "#1f232b"
        Text {
            anchors { left: parent.left; right: parent.right; top: parent.top; margins: 20 * root.u }
            text: "Today"
            color: root.resetArmed ? "#ffffff" : "#aab2bf"
            font.pixelSize: 25 * root.u
        }
        Text {
            anchors { left: parent.left; right: parent.right; verticalCenter: parent.verticalCenter
                      leftMargin: 20 * root.u; rightMargin: 20 * root.u }
            text: root.span(root.today)
            color: "#ffffff"
            font.pixelSize: 38 * root.u
            font.bold: true
        }
        Text {
            anchors { left: parent.left; right: parent.right; bottom: parent.bottom; margins: 20 * root.u }
            elide: Text.ElideRight
            text: root.resetArmed ? "Confirm reset" : "Reset time"
            color: root.resetArmed ? "#ffffff" : "#aab2bf"
            font.pixelSize: 25 * root.u
            font.bold: root.resetArmed
        }
        MouseArea { anchors.fill: parent; onClicked: root.partTapped(2) }
    }

    Rectangle {   // part 3: the menu
        id: morePart
        x: 8 * root.u; y: timePart.y + root.partHeight + root.gap
        width: root.partWidth; height: root.moreHeight
        radius: 20 * root.u
        color: "#2a2f39"
        Text {
            anchors.centerIn: parent
            text: "More\u2026"
            color: "#ffffff"
            font.pixelSize: 28 * root.u
            font.bold: true
        }
        MouseArea { anchors.fill: parent; onClicked: root.partTapped(3) }
    }

    Rectangle {   // the same outline as everywhere else, around the selected part
        visible: root.selectedPart >= 0
        property Item target: root.selectedPart === 0 ? colorPart
                            : (root.selectedPart === 1 ? namePart : (root.selectedPart === 2 ? timePart : morePart))
        x: target.x - 7 * root.u; y: target.y - 7 * root.u
        width: target.width + 14 * root.u; height: target.height + 14 * root.u
        radius: 27 * root.u
        color: "transparent"
        border.color: "#ffffff"
        border.width: 6 * root.u
    }
}
