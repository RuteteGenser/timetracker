import QtQuick
import QtQuick.Window

Window {
    id: win
    width: cfgWidth
    height: cfgHeight
    visible: true
    color: "#101216"
    title: "Time Tracker"
    visibility: cfgFullscreen ? Window.FullScreen : Window.Windowed

    // Layout: the left column and four tiles exactly fill the width.
    readonly property real u: height / 720
    readonly property real colW: width * 200 / 1280
    readonly property real tileW: (width - colW) / 4

    Item {
        id: mainScreen
        anchors.fill: parent
        visible: ctl.screen === "main"

        // The strip: [Settings/Style column][tile][tile]... slides left as a whole.
        // View offset 0 shows the column; offset n >= 1 puts project n at the left edge.
        Item {
            id: strip
            height: parent.height
            width: win.colW + ctl.projectCount * win.tileW
            x: -(ctl.viewOffset === 0 ? 0 : win.colW + ctl.viewOffset * win.tileW)
            Behavior on x { NumberAnimation { duration: 240; easing.type: Easing.OutCubic } }

            Column {
                width: win.colW
                height: parent.height
                ColumnButton {
                    width: parent.width; height: parent.height / 2; u: win.u
                    label: "Settings"; selected: ctl.selected === 0
                    onTapped: ctl.tap(0)
                }
                ColumnButton {
                    width: parent.width; height: parent.height / 2; u: win.u
                    label: "Style"; selected: ctl.selected === 1
                    onTapped: ctl.tap(1)
                }
            }

            Repeater {
                model: projects
                Tile {
                    x: win.colW + index * win.tileW
                    width: win.tileW
                    height: strip.height
                    projectName: model.projectName
                    tileColor: model.tileColor
                    today: model.today
                    elapsed: model.elapsed
                    running: model.running
                    selected: ctl.selected === index + 2
                    onTapped: ctl.tap(index + 2)
                }
            }
        }
    }

    Loader {
        anchors.fill: parent
        active: ctl.screen !== "main"
        sourceComponent: Placeholder {
            title: ctl.screen === "settings" ? "Settings" : "Style"
            note: "Coming in a later milestone. Press the button to go back."
        }
    }
}
