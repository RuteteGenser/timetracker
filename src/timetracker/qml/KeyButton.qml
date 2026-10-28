import QtQuick

// One key of the on-screen keyboard (also used for the Skip / Save buttons).
Rectangle {
    id: root

    property string label
    property bool focused          // outlined: the knob button would press this
    property bool accent           // green (Save)
    property bool danger           // red (Delete)
    property real u: 1

    signal clicked()

    radius: 4 * u
    color: accent ? "#2f9a58" : (danger ? "#b8434d" : (mouse.pressed ? "#4a5160" : "#2a2f39"))

    Text {
        anchors.centerIn: parent
        text: root.label
        color: "#ffffff"
        font.pixelSize: 30 * root.u
        font.bold: true
    }

    Rectangle {
        visible: root.focused
        anchors.fill: parent
        anchors.margins: -4 * root.u
        radius: root.radius + 4 * root.u
        color: "transparent"
        border.color: "#ffffff"
        border.width: 4 * root.u
    }

    MouseArea { id: mouse; anchors.fill: parent; onClicked: root.clicked() }
}
