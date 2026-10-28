import QtQuick

// A vertical list of big rows (Settings, ...). The knob scrolls, the button opens the
// outlined row; the first row is normally Back. The rows come from the controller.
Rectangle {
    id: root
    color: "#101216"

    property real u: height / 720
    readonly property real pad: 15 * width / 1280
    readonly property real rowH: 84 * u
    readonly property real gap: 12 * u

    Text {
        x: root.pad + 8 * root.u; y: root.pad
        height: 60 * root.u
        verticalAlignment: Text.AlignVCenter
        text: ctl.listTitle
        color: "#ffffff"
        font.pixelSize: 40 * root.u
        font.bold: true
    }

    Text {   // an explanation under the title (the clock warning uses it)
        visible: ctl.listNote.length > 0
        x: root.pad + 8 * root.u; y: root.pad + 64 * root.u
        width: root.width - 2 * root.pad - 16 * root.u
        text: ctl.listNote
        color: "#aab2bf"
        font.pixelSize: 28 * root.u
        wrapMode: Text.WordWrap
        maximumLineCount: 3
    }

    Item {   // rows are cut off at the edges of this area, with room left for the outline
        id: view
        x: root.pad; y: root.pad + 70 * root.u + (ctl.listNote.length > 0 ? 120 * root.u : 0)
        width: root.width - 2 * root.pad
        height: root.height - y - root.pad
        clip: true

        Repeater {
            model: ctl.listRows
            Item {
                id: row
                readonly property bool selected: ctl.listSelected === index
                x: 8 * root.u
                y: 8 * root.u + (index - ctl.listOffset) * (root.rowH + root.gap)
                width: view.width - 16 * root.u
                height: root.rowH
                visible: index >= ctl.listOffset

                Rectangle {
                    id: body
                    anchors.fill: parent
                    radius: 20 * root.u
                    color: modelData.kind === "armed" ? "#8b1a1f"
                         : (modelData.kind === "danger" ? "#d9363e" : (modelData.id === "back" ? "#2a2f39" : "#1f232b"))
                    Text {
                        anchors { left: parent.left; verticalCenter: parent.verticalCenter; leftMargin: 28 * root.u }
                        text: modelData.label
                        color: "#ffffff"
                        font.pixelSize: 34 * root.u
                        font.bold: true
                    }
                    Text {
                        anchors { right: parent.right; verticalCenter: parent.verticalCenter; rightMargin: 28 * root.u }
                        text: modelData.value
                        color: "#aab2bf"
                        font.pixelSize: 30 * root.u
                    }
                }
                Rectangle {
                    visible: row.selected
                    anchors.fill: body
                    anchors.margins: -7 * root.u
                    radius: body.radius + 7 * root.u
                    color: "transparent"
                    border.color: "#ffffff"
                    border.width: 6 * root.u
                }
                MouseArea { anchors.fill: parent; onClicked: ctl.tap(index) }
            }
        }
    }
}
