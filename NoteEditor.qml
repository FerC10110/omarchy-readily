import QtQuick
import QtQuick.Controls
import Quickshell
import Quickshell.Wayland
import qs.Commons
import qs.Ui
import "ReadilyModel.js" as Model

// A tiny Markdown editor for one section's note, in a floating window over a
// dimmed background, like the panel's keybinding card. The note is read and
// written by bin/readily (`read` and `write`): the stamp `read` returns goes
// back with `write`, so a note that changed on disk meanwhile is never
// overwritten. Closing discards unsaved edits, but only on the second try.
PanelWindow {
  id: root

  property var host: null
  property bool opened: false
  property string section: ""
  property string stamp: ""        // hash of the loaded note, sent back on save
  property string loadedText: ""
  property string notice: ""
  property bool noticeIsError: false
  property bool closeArmed: false

  readonly property color fg: host ? host.foreground : Color.foreground
  readonly property color dim: host ? host.dim : Qt.darker(Color.foreground, 1.55)
  readonly property color urgent: host ? host.urgent : Color.urgent
  readonly property string family: host ? host.fontFamily : Style.font.family
  readonly property bool busy: readCmd.running || writeCmd.running
  readonly property bool dirty: opened && stamp !== "" && area.text !== loadedText

  visible: opened
  color: "transparent"
  exclusionMode: ExclusionMode.Ignore
  anchors { top: true; bottom: true; left: true; right: true }
  WlrLayershell.namespace: "io.github.ferc10110.readily.editor"
  WlrLayershell.layer: WlrLayer.Overlay
  WlrLayershell.keyboardFocus: visible ? WlrKeyboardFocus.Exclusive : WlrKeyboardFocus.None

  function focusArea() {
    Qt.callLater(function() {
      if (root.opened && !root.busy) area.forceActiveFocus()
    })
  }

  function setNotice(message, isError) {
    notice = message || ""
    noticeIsError = isError === true
  }

  function openSection(name) {
    if (!name || readCmd.running) return
    section = name
    stamp = ""
    loadedText = ""
    area.text = ""
    closeArmed = false
    setNotice("Loading…", false)
    opened = true
    readCmd.start(["read", "--json", "--", name])
  }

  function reload() {
    if (readCmd.running) return
    closeArmed = false
    setNotice("Loading…", false)
    readCmd.start(["read", "--json", "--", section])
  }

  function save() {
    if (!opened || writeCmd.running || stamp === "" || !dirty) return
    closeArmed = false
    setNotice("", false)
    // The text goes over stdin, never argv; the byte count tells the command
    // how much to read, since this process never closes its stdin. Options
    // come before `--`: everything after it is read as positionals.
    writeCmd.stdinText = area.text
    writeCmd.start(["write", "--expect=" + stamp, "--bytes=" + Model.utf8Length(area.text),
                    "--", section])
  }

  function requestClose() {
    if (writeCmd.running) return
    if (dirty && !closeArmed) {
      closeArmed = true
      setNotice("Unsaved changes; close again to discard them", false)
      return
    }
    opened = false
  }

  onOpenedChanged: if (!opened) {
    stamp = ""
    loadedText = ""
    area.text = ""
    closeArmed = false
    setNotice("", false)
  }

  ReadilyCommand {
    id: readCmd
    program: root.host ? root.host.program : ""
    onFinished: function(code, out, err) {
      var data = root.host ? root.host.parseJson(out) : null
      if (code !== 0 || !data) {
        root.setNotice(root.host ? (root.host.lastLine(err) || "Could not read the note")
                                 : "Could not read the note", true)
        return
      }
      root.loadedText = data.text
      root.stamp = data.stamp
      area.text = data.text
      root.setNotice("", false)
      root.focusArea()
    }
  }

  ReadilyCommand {
    id: writeCmd
    program: root.host ? root.host.program : ""
    onFinished: function(code, out, err) {
      if (code === 0) {
        root.opened = false
        if (root.host) {
          root.host.loadList()
          Quickshell.execDetached(["notify-send", "Readily", "Saved " + root.section])
        }
        return
      }
      root.setNotice(root.host ? (root.host.lastLine(err) || "Could not save the note")
                               : "Could not save the note", true)
    }
  }

  onVisibleChanged: if (visible) root.focusArea()

  Rectangle {
    anchors.fill: parent
    color: Color.menu.scrim
  }

  MouseArea {
    anchors.fill: parent
    acceptedButtons: Qt.AllButtons
    enabled: root.opened && !root.busy
    onClicked: root.requestClose()
  }

  BorderSurface {
    id: card
    anchors.centerIn: parent
    width: Math.round(Math.min(Style.space(560), root.width - Style.gapsOut * 2))
    height: Math.round(Math.min(Style.space(540), root.height - Style.gapsOut * 2))
    color: Color.popups.background
    padding: Style.spacing.popupPadding
    radius: Style.cornerRadius

    // Clicks on the card stay on the card.
    MouseArea {
      anchors.fill: parent
      acceptedButtons: Qt.AllButtons
      enabled: !root.busy
    }

    Column {
      x: card.contentLeftInset
      y: card.contentTopInset
      width: card.width - card.contentLeftInset - card.contentRightInset
      height: card.height - card.contentTopInset - card.contentBottomInset
      spacing: Style.space(6)

      Item {
        id: header
        width: parent.width
        height: Math.max(titleText.implicitHeight, headerButtons.implicitHeight)

        Text {
          id: titleText
          anchors.left: parent.left
          anchors.verticalCenter: parent.verticalCenter
          width: parent.width - headerButtons.width - Style.space(8)
          text: root.section + (root.dirty ? "  •" : "")
          textFormat: Text.PlainText
          elide: Text.ElideRight
          color: root.fg
          font.family: root.family
          font.pixelSize: Style.font.body
          font.bold: true
        }

        Row {
          id: headerButtons
          anchors.right: parent.right
          anchors.verticalCenter: parent.verticalCenter
          spacing: Style.space(4)

          Button {
            text: "Reload"
            iconText: "󰑐"
            bordered: true
            enabled: !root.busy
            opacity: enabled ? 1 : 0.55
            tooltipText: "Read the note from disk again, discarding edits"
            foreground: root.fg
            fontFamily: root.family
            onClicked: root.reload()
          }

          Button {
            text: "Save"
            iconText: "󰆓"
            bordered: true
            enabled: root.dirty && !root.busy
            opacity: enabled ? 1 : 0.55
            tooltipText: "Save the note (Ctrl+S)"
            foreground: root.fg
            fontFamily: root.family
            onClicked: root.save()
          }

          Button {
            text: "Close"
            iconText: "󰅁"
            bordered: true
            enabled: !writeCmd.running
            opacity: enabled ? 1 : 0.55
            tooltipText: "Close the editor (Esc)"
            foreground: root.fg
            fontFamily: root.family
            onClicked: root.requestClose()
          }
        }
      }

      Item {
        width: parent.width
        height: parent.height - header.height - footer.height - 2 * parent.spacing

        TextArea {
          id: area
          anchors.fill: parent
          enabled: !root.busy
          color: root.fg
          selectionColor: Style.selectionFillFor(root.fg, Color.accent)
          selectedTextColor: root.fg
          wrapMode: TextArea.Wrap
          textFormat: TextArea.PlainText
          persistentSelection: false
          font.family: root.family
          font.pixelSize: Style.font.body
          background: null

          Keys.onPressed: function(event) {
            var ctrl = (event.modifiers & Qt.ControlModifier) !== 0
            if (ctrl && event.key === Qt.Key_S) {
              root.save()
              event.accepted = true
            } else if (event.key === Qt.Key_Escape) {
              root.requestClose()
              event.accepted = true
            }
          }
        }
      }

      Item {
        id: footer
        width: parent.width
        height: Math.max(hint.implicitHeight, statusText.implicitHeight)

        Text {
          id: hint
          anchors.left: parent.left
          anchors.verticalCenter: parent.verticalCenter
          width: parent.width - statusText.implicitWidth - Style.space(8)
          visible: root.notice === "" && !root.dirty
          text: "Ctrl+S save · Esc close · one item per code block"
          textFormat: Text.PlainText
          elide: Text.ElideRight
          color: root.dim
          font.family: root.family
          font.pixelSize: Style.font.caption
        }

        Text {
          id: statusText
          anchors.right: parent.right
          anchors.verticalCenter: parent.verticalCenter
          visible: text !== ""
          text: root.notice !== "" ? root.notice
            : (root.busy ? "Working…" : (root.dirty ? "Unsaved changes" : ""))
          textFormat: Text.PlainText
          elide: Text.ElideRight
          color: root.notice !== "" && root.noticeIsError ? root.urgent : root.dim
          font.family: root.family
          font.pixelSize: Style.font.caption
        }
      }
    }
  }
}
