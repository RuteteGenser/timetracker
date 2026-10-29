import QtQuick

// Every entry of the day / week / month, grouped per project (alphabetical, earliest entry first,
// with its note), under the controls and the total.
// Knob: the period is "live" when the screen opens (blue): turning goes to the previous / next
// period. Pressing it leaves live mode: turning then moves the outline over Back, Day, Week, Month,
// Entries, the period and down the entry list; pressing an entry opens the editor, pressing the
// period (or a Day / Week / Month button) is live again.
// Touch: tap the buttons, the arrows beside the period, or an entry.
Rectangle {
    id: root
    color: "#101216"

    property real u: height / 720
    readonly property real pad: 15 * width / 1280
    readonly property real gap: 12 * u
    readonly property real buttonW: 150 * u
    readonly property var kinds: ["day", "week", "month"]
    readonly property var kindLabels: ["Day", "Week", "Month"]

    // Under an hour show minutes and seconds; from an hour up, hours and minutes.
    function span(s) {
        if (s <= 0) return "–"
        if (s < 60) return s + "s"
        var m = Math.floor(s / 60)
        if (s < 3600) return m + "m " + (s % 60 < 10 ? "0" : "") + (s % 60) + "s"
        return Math.floor(s / 3600) + "h " + (m % 60 < 10 ? "0" : "") + (m % 60) + "m"
    }

    Row {   // first row: Back, Day, Week, Month and Entries
        id: controls
        x: root.pad; y: root.pad
        spacing: root.gap

        KeyButton {
            u: root.u; width: root.buttonW; height: 76 * root.u
            label: "Back"; focused: ctl.repFocus === 0
            onClicked: ctl.repTap(0)
        }
        Repeater {
            model: 3
            KeyButton {
                u: root.u; width: root.buttonW; height: 76 * root.u
                label: root.kindLabels[index]
                focused: ctl.repFocus === index + 1
                color: ctl.repKind === root.kinds[index] ? "#3274d1" : "#2a2f39"
                onClicked: ctl.repTap(index + 1)
            }
        }
        KeyButton {
            u: root.u; width: root.buttonW; height: 76 * root.u
            label: "Entries"; focused: ctl.repFocus === 4
            onClicked: ctl.repTap(4)
        }
    }

    Row {   // second row: the period (older, label, newer) and the total
        x: root.pad; y: root.pad + 88 * root.u
        spacing: root.gap

        KeyButton {   // older
            u: root.u; width: 76 * root.u; height: 76 * root.u
            label: "\u25c0"; opacity: ctl.repCanOlder ? 1 : 0.35
            onClicked: ctl.repStep(-1)
        }
        Rectangle {   // the period being shown
            width: 480 * root.u
            height: 76 * root.u
            radius: 4 * root.u
            color: ctl.repStepping ? "#3274d1" : "#1f232b"
            Text {
                anchors { fill: parent; leftMargin: 10 * root.u; rightMargin: 10 * root.u }
                horizontalAlignment: Text.AlignHCenter
                verticalAlignment: Text.AlignVCenter
                text: ctl.repLabel
                color: "#ffffff"
                font.pixelSize: 30 * root.u
                font.bold: true
                fontSizeMode: Text.Fit
                minimumPixelSize: Math.max(1, 16 * root.u)
            }
            Rectangle {
                visible: ctl.repFocus === 5
                anchors.fill: parent
                radius: parent.radius
                color: "transparent"
                border.color: "#ffffff"
                border.width: 6 * root.u
            }
            MouseArea { anchors.fill: parent; onClicked: ctl.repTap(5) }
        }
        KeyButton {   // newer
            u: root.u; width: 76 * root.u; height: 76 * root.u
            label: "\u25b6"; opacity: ctl.repCanNewer ? 1 : 0.35
            onClicked: ctl.repStep(1)
        }
        Item { width: 20 * root.u; height: 1 }
        Text {
            anchors.verticalCenter: parent.verticalCenter
            text: "Total"
            color: "#aab2bf"
            font.pixelSize: 30 * root.u
        }
        Text {
            anchors.verticalCenter: parent.verticalCenter
            text: root.span(ctl.repTotal)
            color: "#ffffff"
            font.pixelSize: 52 * root.u
            font.bold: true
        }
    }

    // The list under the controls. It scrolls (no animation) just enough to keep the outlined
    // entry in view, with its group header when it is the first of its group.
    Item {
        id: chart
        x: root.pad; y: root.pad + 180 * root.u
        width: root.width - 2 * root.pad
        height: root.height - y - root.pad
        clip: true

        property real scrollY: 0
        property string periodKey: ""

        function ensureVisible() {
            var key = ctl.repKind + "|" + ctl.repLabel
            if (key !== periodKey) {      // another period: start at the top
                periodKey = key
                scrollY = 0
            }
            var k = ctl.repFocus - 6
            if (k >= 0) {
                for (var i = 0; i < rows.count; i++) {
                    var row = rows.itemAt(i)
                    if (row && row.isEntry && row.entryK === k) {
                        var top = row.y, bottom = row.y + row.height
                        var before = i > 0 ? rows.itemAt(i - 1) : null
                        if (before && !before.isEntry) top = before.y   // the group header comes along
                        if (top < scrollY) scrollY = top
                        else if (bottom > scrollY + height) scrollY = bottom - height
                        break
                    }
                }
            }
            scrollY = Math.max(0, Math.min(scrollY, Math.max(0, column.height - height)))
        }
        Connections {
            target: ctl
            function onRepChanged() { Qt.callLater(chart.ensureVisible) }
        }
        Component.onCompleted: ensureVisible()

        Text {
            visible: ctl.repItems.length === 0
            anchors.centerIn: parent
            text: "Nothing tracked in this period"
            color: "#6b7380"
            font.pixelSize: 32 * root.u
        }

        Column {
            id: column
            y: -chart.scrollY
            width: chart.width
            spacing: 6 * root.u

            Repeater {
                id: rows
                model: ctl.repItems

                Item {
                    id: row
                    readonly property bool isEntry: modelData.kind === "entry"
                    readonly property int entryK: isEntry ? modelData.k : -1
                    readonly property bool focused: isEntry && ctl.repFocus === 6 + modelData.k
                    width: column.width
                    height: isEntry ? card.height : 50 * root.u

                    // group header: colour dot, project, and its total on the right
                    Item {
                        visible: !row.isEntry
                        anchors.fill: parent
                        Rectangle {
                            x: 10 * root.u; anchors.verticalCenter: parent.verticalCenter
                            width: 22 * root.u; height: 22 * root.u; radius: 11 * root.u
                            color: modelData.color || "#ffffff"
                        }
                        Text {
                            x: 46 * root.u; width: parent.width - 300 * root.u; height: parent.height
                            verticalAlignment: Text.AlignVCenter
                            text: modelData.name || ""
                            color: "#ffffff"; font.pixelSize: 30 * root.u; font.bold: true
                            elide: Text.ElideRight
                        }
                        Text {
                            anchors { right: parent.right; rightMargin: 14 * root.u }
                            height: parent.height
                            verticalAlignment: Text.AlignVCenter
                            text: modelData.total || ""
                            color: "#aab2bf"; font.pixelSize: 28 * root.u
                        }
                    }

                    // entry: time range and duration, then the note (two lines at most)
                    Rectangle {
                        id: card
                        visible: row.isEntry
                        x: 8 * root.u; width: parent.width - 16 * root.u
                        height: Math.max(58 * root.u, texts.height + 20 * root.u)
                        radius: 4 * root.u
                        color: "#1f232b"

                        Rectangle {   // the project's colour along the left edge
                            width: 6 * root.u; height: parent.height
                            color: modelData.color || "#ffffff"
                        }
                        Column {
                            id: texts
                            x: 24 * root.u; y: 10 * root.u
                            width: parent.width - 48 * root.u
                            spacing: 2 * root.u
                            Item {
                                width: parent.width; height: 34 * root.u
                                Text {
                                    text: modelData.time || ""
                                    color: "#ffffff"; font.pixelSize: 28 * root.u; font.bold: true
                                }
                                Text {
                                    anchors.right: parent.right
                                    text: modelData.duration || ""
                                    color: "#aab2bf"; font.pixelSize: 28 * root.u
                                }
                            }
                            Text {
                                visible: (modelData.note || "").length > 0
                                width: parent.width
                                text: modelData.note || ""
                                color: "#d5dbe5"; font.pixelSize: 26 * root.u
                                wrapMode: Text.Wrap
                                maximumLineCount: 2
                                elide: Text.ElideRight
                            }
                        }
                        Rectangle {   // the outline: the knob is on this entry
                            visible: row.focused
                            anchors.fill: parent
                            radius: parent.radius
                            color: "transparent"
                            border.color: "#ffffff"; border.width: 5 * root.u
                        }
                        MouseArea { anchors.fill: parent; onClicked: ctl.repTapEntry(row.entryK) }
                    }
                }
            }
        }
    }
}
