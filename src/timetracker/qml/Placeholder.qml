import QtQuick

// Stand-in for screens that arrive in later milestones.
Rectangle {
    id: root
    property string title
    property string note
    color: "#101216"

    Column {
        anchors.centerIn: parent
        spacing: 24
        Text { anchors.horizontalCenter: parent.horizontalCenter; text: root.title
               color: "#ffffff"; font.pixelSize: 56; font.bold: true }
        Text { anchors.horizontalCenter: parent.horizontalCenter; text: root.note
               color: "#aab2bf"; font.pixelSize: 28 }
        Rectangle {
            anchors.horizontalCenter: parent.horizontalCenter
            width: 260; height: 90; radius: 20; color: "#2a2f39"
            border.color: "#ffd84d"; border.width: 5
            Text { anchors.centerIn: parent; text: "Back"; color: "#ffffff"
                   font.pixelSize: 34; font.bold: true }
            MouseArea { anchors.fill: parent; onClicked: ctl.back() }
        }
    }
}
