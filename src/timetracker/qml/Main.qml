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

    // Layout: five equal slots fill the width: the Settings/Style column and four project cards.
    readonly property real u: height / 720
    readonly property real tileW: width / 5
    readonly property real colW: tileW

    Item {
        id: mainScreen
        anchors.fill: parent
        visible: ctl.screen === "main"

        // The strip: [Settings/Style column][card][card]... slides left as a whole.
        // View offset n = number of slots scrolled off to the left.
        Item {
            id: strip
            height: parent.height
            width: (ctl.projectCount + 1) * win.tileW
            x: -ctl.viewOffset * win.tileW
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
                    x: (index + 1) * win.tileW
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

    NotePrompt {
        anchors.fill: parent
        visible: ctl.notePromptOpen
    }
}
