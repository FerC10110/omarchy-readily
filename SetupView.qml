import QtQuick
import qs.Commons
import qs.Ui
import "ReadilyModel.js" as Model

// First run, or when the folder went missing: pick where the sections live.
// Obsidian vaults come first because that is where the notes are nicest to
// edit, but any folder works.
Item {
  id: view

  property var host: null
  property int choice: 0
  property bool choosingAnother: false

  readonly property Item focusItem: choice === options.length ? otherField : keys
  readonly property var options: host ? host.suggestions : []
  readonly property color fg: host ? host.foreground : Color.foreground
  readonly property color dim: host ? host.dim : Qt.darker(Color.foreground, 1.55)
  readonly property color urgent: host ? host.urgent : Color.urgent
  readonly property string family: host ? host.fontFamily : Style.font.family
  readonly property bool folderMissing: host !== null && host.where.folder !== ""
    && host.where.exists === false && host.where.error === ""
  readonly property string chosenPath: choice < options.length ? options[choice].path : otherField.text.trim()

  implicitHeight: column.implicitHeight

  function resetChoice() {
    choice = 0
    choosingAnother = false
    otherField.text = ""
  }

  function move(delta) {
    choice = Math.max(0, Math.min(options.length, choice + delta))
    if (choice === options.length) otherField.forceActiveFocus()
    else keys.forceActiveFocus()
  }

  function handleKey(event) {
    if (event.key === Qt.Key_Down) {
      move(1)
      event.accepted = true
    } else if (event.key === Qt.Key_Up) {
      move(-1)
      event.accepted = true
    } else if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter) {
      if (folderMissing && !choosingAnother) host.chooseFolder(host.where.folder)
      else host.chooseFolder(chosenPath)
      event.accepted = true
    } else if (event.key === Qt.Key_Escape) {
      host.close()
      event.accepted = true
    }
  }

  // Holds keyboard focus while a suggestion (not the text field) is chosen.
  Item {
    id: keys
    focus: true
    Keys.onPressed: function(event) { view.handleKey(event) }
  }

  Column {
    id: column
    width: parent.width
    spacing: Style.space(8)

    Text {
      text: "Readily"
      textFormat: Text.PlainText
      color: view.fg
      font.family: view.family
      font.pixelSize: Style.font.title
      font.bold: true
    }

    Text {
      width: parent.width
      text: view.folderMissing && !view.choosingAnother
        ? "Folder not found: " + Model.tildePath(view.host.where.folder, view.host.home)
        : "Where should Readily keep your sections?"
      textFormat: Text.PlainText
      wrapMode: Text.WordWrap
      color: view.fg
      font.family: view.family
      font.pixelSize: Style.font.body
    }

    Row {
      visible: view.folderMissing && !view.choosingAnother
      spacing: Style.space(6)

      Button {
        text: "Create it"
        bordered: true
        foreground: view.fg
        fontFamily: view.family
        onClicked: view.host.chooseFolder(view.host.where.folder)
      }

      Button {
        text: "Choose another"
        bordered: true
        foreground: view.fg
        fontFamily: view.family
        onClicked: view.choosingAnother = true
      }
    }

    Column {
      width: parent.width
      spacing: Style.space(4)
      visible: !view.folderMissing || view.choosingAnother

      Repeater {
        model: view.options

        Button {
          required property var modelData
          required property int index
          width: parent.width
          leftAlign: true
          selected: view.choice === index
          text: (view.choice === index ? "◉  " : "○  ") + Model.tildePath(modelData.path, view.host.home)
            + "   " + modelData.label
          foreground: view.fg
          fontFamily: view.family
          onClicked: {
            view.choice = index
            keys.forceActiveFocus()
          }
        }
      }

      Button {
        width: parent.width
        leftAlign: true
        selected: view.choice === view.options.length
        text: (view.choice === view.options.length ? "◉  " : "○  ") + "Other folder…"
        foreground: view.fg
        fontFamily: view.family
        onClicked: {
          view.choice = view.options.length
          otherField.forceActiveFocus()
        }
      }

      TextField {
        id: otherField
        width: parent.width
        visible: view.choice === view.options.length
        placeholderText: "~/path/to/Readily"
        foreground: view.fg
        font.family: view.family
        Keys.onPressed: function(event) { view.handleKey(event) }
      }

      Text {
        width: parent.width
        text: "One Markdown note per section. Inside an Obsidian vault you can edit them there too."
        textFormat: Text.PlainText
        wrapMode: Text.WordWrap
        color: view.dim
        font.family: view.family
        font.pixelSize: Style.font.caption
      }

      Button {
        text: "Use this folder"
        bordered: true
        enabled: view.chosenPath !== ""
        opacity: enabled ? 1 : 0.55
        foreground: view.fg
        fontFamily: view.family
        onClicked: view.host.chooseFolder(view.chosenPath)
      }
    }

    Text {
      width: parent.width
      visible: text !== ""
      text: view.host ? view.host.notice : ""
      textFormat: Text.PlainText
      wrapMode: Text.WordWrap
      color: view.urgent
      font.family: view.family
      font.pixelSize: Style.font.bodySmall
    }
  }
}
