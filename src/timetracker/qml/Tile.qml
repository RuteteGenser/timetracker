import QtQuick

// One project tile. A running tile is filled with the project colour, shows the
// live timer and has a pulsing white ring so it is obvious from across the desk.
Item {
    id: root

    property string projectName
    property color tileColor
    property int today          // seconds worked today
    property int elapsed        // seconds since start, only meaningful while running
    property bool running
    property bool selected
    property real u: height / 720   // UI scale

    signal tapped()

    function pad(n) { return n < 10 ? "0" + n : "" + n }
    function clock(s) {
        return pad(Math.floor(s / 3600)) + ":" + pad(Math.floor(s / 60) % 60) + ":" + pad(s % 60)
    }
    // Under an hour show minutes and seconds, so even a short timer visibly adds up.
    function span(s) {
        if (s < 3600)
            return Math.floor(s / 60) + "m " + pad(s % 60) + "s"
        return Math.floor(s / 3600) + "h " + pad(Math.floor(s / 60) % 60) + "m"
    }

    Rectangle {
        id: body
        anchors.fill: parent
        anchors.margins: 8 * root.u
        radius: 20 * root.u
        color: root.running ? root.tileColor : "#1f232b"
        clip: true

        // Colour band on idle tiles: a rounded rectangle whose lower, rounded part
        // is covered, so only the top corners stay round (clip: is rectangular).
        Rectangle {
            visible: !root.running
            width: parent.width
            height: 26 * root.u + body.radius
            radius: body.radius
            color: root.tileColor
        }
        Rectangle {
            visible: !root.running
            y: 26 * root.u
            width: parent.width
            height: body.radius
            color: body.color
        }

        Text {
            anchors { left: parent.left; right: parent.right; top: parent.top
                      margins: 24 * root.u; topMargin: 64 * root.u }
            text: root.projectName
            color: "#ffffff"
            font.pixelSize: 36 * root.u
            font.bold: true
            wrapMode: Text.Wrap       // a long name wraps onto a second line
            maximumLineCount: 2
            elide: Text.ElideRight
        }

        Text {   // static marker: no animation, the Pi should stay idle
            visible: root.running
            anchors { left: parent.left; right: parent.right; top: parent.top
                      margins: 24 * root.u; topMargin: 170 * root.u }
            text: "\u25cf RUNNING"
            color: "#ffffff"
            font.pixelSize: 24 * root.u
            font.bold: true
        }

        Text {
            visible: root.running
            anchors.centerIn: parent
            text: root.clock(root.elapsed)
            color: "#ffffff"
            font.pixelSize: 38 * root.u
            font.bold: true
            font.family: "monospace"
        }

        Text {
            anchors { left: parent.left; right: parent.right; bottom: parent.bottom
                      margins: 20 * root.u }
            text: "Today " + root.span(root.today)
            color: root.running ? "#ffffff" : "#aab2bf"
            font.pixelSize: 25 * root.u
            elide: Text.ElideRight
        }
    }

    Rectangle {   // selection outline
        visible: root.selected
        anchors.fill: body
        anchors.margins: -7 * root.u
        radius: body.radius + 7 * root.u
        color: "transparent"
        border.color: "#ffffff"
        border.width: 6 * root.u
    }

    MouseArea { anchors.fill: parent; onClicked: root.tapped() }
}
