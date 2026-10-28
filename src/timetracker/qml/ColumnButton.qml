import QtQuick

// One of the two stacked buttons at the far left (Settings, Style).
Item {
    id: root

    property string label
    property bool selected
    property real u: 1

    signal tapped()

    Rectangle {
        id: body
        anchors.fill: parent
        anchors.margins: 8 * root.u
        radius: 20 * root.u
        color: "#2a2f39"

        Text {
            anchors.centerIn: parent
            text: root.label
            color: "#ffffff"
            font.pixelSize: 30 * root.u
            font.bold: true
        }
    }

    Rectangle {
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
