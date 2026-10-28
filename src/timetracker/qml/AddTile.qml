import QtQuick

// The "+" card after the last project on the Style screen: press to add a project.
Item {
    id: root

    property bool selected
    property real u: 1

    signal tapped()

    Rectangle {
        id: body
        anchors.fill: parent
        anchors.margins: 8 * root.u
        radius: 20 * root.u
        color: "#1f232b"

        Text {
            anchors.centerIn: parent
            anchors.verticalCenterOffset: -20 * root.u
            text: "+"
            color: "#ffffff"
            font.pixelSize: 110 * root.u
            font.bold: true
        }
        Text {
            anchors { horizontalCenter: parent.horizontalCenter; bottom: parent.bottom; bottomMargin: 40 * root.u }
            text: "New project"
            color: "#aab2bf"
            font.pixelSize: 28 * root.u
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
