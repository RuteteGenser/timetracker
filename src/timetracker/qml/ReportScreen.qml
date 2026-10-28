import QtQuick

// Day / week / month totals as a bar chart, one bar per project and a total on top.
// Knob: turn moves the outline over Back, Day, Week, Month and the period; pressing a kind
// selects it, pressing the period starts "stepping" (turn = older / newer, press to stop).
// Touch: tap the buttons, and use the arrows beside the period.
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

    function maxSeconds() {
        var m = 1
        for (var i = 0; i < ctl.repRows.length; i++) m = Math.max(m, ctl.repRows[i].seconds)
        return m
    }

    Row {   // Back, Day, Week, Month, then the period selector
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
        KeyButton {   // older
            u: root.u; width: 76 * root.u; height: 76 * root.u
            label: "◀"; opacity: ctl.repCanOlder ? 1 : 0.35
            onClicked: ctl.repStep(-1)
        }
        Rectangle {   // the period being shown
            width: root.width - 2 * root.pad - 4 * (root.buttonW + root.gap) - 2 * (76 * root.u + root.gap)
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
                visible: ctl.repFocus === 4
                anchors.fill: parent
                radius: parent.radius
                color: "transparent"
                border.color: "#ffffff"
                border.width: 6 * root.u
            }
            MouseArea { anchors.fill: parent; onClicked: ctl.repTap(4) }
        }
        KeyButton {   // newer
            u: root.u; width: 76 * root.u; height: 76 * root.u
            label: "▶"; opacity: ctl.repCanNewer ? 1 : 0.35
            onClicked: ctl.repStep(1)
        }
    }

    Row {   // the total
        x: root.pad + 8 * root.u; y: root.pad + 96 * root.u
        spacing: 20 * root.u
        Text {
            anchors.baseline: totalText.baseline
            text: "Total"
            color: "#aab2bf"
            font.pixelSize: 30 * root.u
        }
        Text {
            id: totalText
            text: root.span(ctl.repTotal)
            color: "#ffffff"
            font.pixelSize: 56 * root.u
            font.bold: true
        }
    }

    Item {   // the bars
        id: chart
        x: root.pad; y: root.pad + 190 * root.u
        width: root.width - 2 * root.pad
        height: root.height - y - root.pad
        readonly property real rowH: Math.min(64 * root.u, height / Math.max(1, ctl.repRows.length))
        readonly property real nameW: 250 * root.u
        readonly property real valueW: 170 * root.u
        readonly property real barW: width - nameW - valueW - 20 * root.u

        Text {
            visible: ctl.repTotal === 0
            anchors.centerIn: parent
            text: "Nothing tracked in this period"
            color: "#6b7380"
            font.pixelSize: 32 * root.u
        }

        Repeater {
            model: ctl.repTotal === 0 ? [] : ctl.repRows
            Item {
                y: index * chart.rowH
                width: chart.width
                height: chart.rowH

                Text {
                    x: 8 * root.u
                    width: chart.nameW - 16 * root.u
                    height: parent.height
                    verticalAlignment: Text.AlignVCenter
                    text: modelData.name + (modelData.archived ? " (archived)" : "")
                    color: modelData.archived ? "#aab2bf" : "#ffffff"
                    font.pixelSize: 28 * root.u
                    elide: Text.ElideRight
                }
                Rectangle {
                    x: chart.nameW
                    anchors.verticalCenter: parent.verticalCenter
                    height: Math.min(parent.height * 0.62, 40 * root.u)
                    width: Math.max(modelData.seconds > 0 ? 6 * root.u : 0, chart.barW * modelData.seconds / root.maxSeconds())
                    radius: 3 * root.u
                    color: modelData.color
                }
                Text {
                    x: chart.nameW + chart.barW + 20 * root.u
                    width: chart.valueW
                    height: parent.height
                    verticalAlignment: Text.AlignVCenter
                    text: root.span(modelData.seconds)
                    color: modelData.seconds > 0 ? "#ffffff" : "#6b7380"
                    font.pixelSize: 28 * root.u
                }
            }
        }
    }
}
