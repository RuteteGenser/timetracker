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

    // Layout: a margin all round, so nothing (the selection outline included) touches the
    // screen edge; inside it five equal slots: the Settings/Style column and four project cards.
    readonly property real u: height / 720
    readonly property real pad: 15 * width / 1280
    readonly property real tileW: (width - 2 * pad) / 5
    readonly property real colW: tileW

    Item {
        id: mainScreen
        anchors.fill: parent
        visible: ctl.screen === "main" || ctl.screen === "style"

        // Cards scrolled out of view are cut off at the margin, not drawn into it.
        Item {
            id: viewport
            x: win.pad; y: win.pad
            width: win.width - 2 * win.pad
            height: win.height - 2 * win.pad
            clip: true

        // The strip: [Settings/Style/Reports column][card][card]... slides left as a whole.
        // View offset n = number of slots scrolled off to the left.
        Item {
            id: strip
            height: parent.height
            width: (ctl.projectCount + 1) * win.tileW
            x: -ctl.viewOffset * win.tileW
            Behavior on x { NumberAnimation { duration: 240; easing.type: Easing.OutCubic } }

            Column {   // main screen: Settings, Style and Reports
                visible: ctl.screen === "main"
                width: win.colW
                height: parent.height
                ColumnButton {
                    width: parent.width; height: parent.height / 3; u: win.u
                    label: "Settings"; selected: ctl.selected === 0
                    onTapped: ctl.tap(0)
                }
                ColumnButton {
                    width: parent.width; height: parent.height / 3; u: win.u
                    label: "Style"; selected: ctl.selected === 1
                    onTapped: ctl.tap(1)
                }
                ColumnButton {
                    width: parent.width; height: parent.height / 3; u: win.u
                    label: "Reports"; selected: ctl.selected === 2
                    onTapped: ctl.tap(2)
                }
            }

            ColumnButton {   // style screen: one Back button
                visible: ctl.screen === "style"
                width: win.colW; height: parent.height; u: win.u
                label: "Back"; selected: ctl.selected === 0
                onTapped: ctl.tap(0)
            }

            Repeater {
                model: ctl.screen === "main" ? projects : 0
                Tile {
                    x: (index + 1) * win.tileW
                    width: win.tileW
                    height: strip.height
                    u: win.u
                    projectName: model.projectName
                    tileColor: model.tileColor
                    today: model.today
                    elapsed: model.elapsed
                    running: model.running
                    selected: ctl.selectedCard === index
                    onTapped: ctl.tap(ctl.firstItem + index)
                }
            }

            // Style screen: every card is split into colour, name and time.
            Repeater {
                model: ctl.screen === "style" ? projects : 0
                StyleTile {
                    x: (index + 1) * win.tileW
                    width: win.tileW
                    height: strip.height
                    u: win.u
                    projectName: model.projectName
                    tileColor: model.tileColor
                    today: model.today
                    selectedPart: ctl.selectedCard === index ? ctl.selectedPart : -1
                    resetArmed: ctl.resetArmed && ctl.selectedCard === index
                    onPartTapped: (part) => ctl.tap(1 + 3 * index + part)
                }
            }
        }
        }
    }

    ListScreen {
        anchors.fill: parent
        visible: ctl.screenIsList
    }

    Loader {   // screens that are not built yet
        anchors.fill: parent
        active: ctl.screen !== "main" && ctl.screen !== "style" && !ctl.screenIsList
        sourceComponent: Placeholder {
            title: ctl.screen === "reports" ? "Reports" : (ctl.screen === "datetime" ? "Date & time" : "Status")
            note: "Coming soon. Press the button to go back."
        }
    }

    NotePrompt {
        anchors.fill: parent
        visible: ctl.notePromptOpen
    }
}
