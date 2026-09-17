import QtQuick
import qs.Commons
import qs.Ui
import "ReadilyModel.js" as Model

// One item: its title, a line of description, the first lines of its content
// (or a thumbnail) and its tags. A click on a tag filters by that tag; a click
// anywhere else copies the item; a right-click opens the note in the editor.
Rectangle {
  id: row

  property var host: null
  property var entry: null
  property bool selected: false
  property bool showSection: false

  signal activated()
  signal editRequested()
  signal tagClicked(string tag)

  readonly property color fg: host ? host.foreground : Color.foreground
  readonly property color dim: host ? host.dim : Qt.darker(Color.foreground, 1.55)
  readonly property color urgent: host ? host.urgent : Color.urgent
  readonly property string family: host ? host.fontFamily : Style.font.family
  readonly property var info: entry ? entry.item : ({})
  readonly property var preview: Model.rowPreview(info)
  readonly property bool usable: info.missing !== true
  readonly property var chips: (info.tags || []).map(function(t) { return { name: t, inherited: false } })
    .concat((info.inheritedTags || []).map(function(t) { return { name: t, inherited: true } }))

  implicitHeight: content.implicitHeight + Style.space(12)
  radius: Style.cornerRadius
  opacity: usable ? 1 : 0.6
  color: selected ? Style.selectionFillFor(fg, Color.accent)
    : (hover.containsMouse ? Style.hoverFillFor(fg, Color.accent) : "transparent")

  MouseArea {
    id: hover
    anchors.fill: parent
    hoverEnabled: true
    acceptedButtons: Qt.LeftButton | Qt.RightButton
    cursorShape: row.usable ? Qt.PointingHandCursor : Qt.ArrowCursor
    onClicked: function(mouse) {
      if (!row.usable) return
      if (mouse.button === Qt.RightButton) row.editRequested()
      else row.activated()
    }
  }

  Row {
    id: content
    x: Style.space(8)
    y: Style.space(6)
    width: row.width - Style.space(16)
    spacing: Style.space(8)

    Image {
      id: thumb
      visible: row.info.kind === "image" && row.info.image !== ""
      width: visible ? Style.space(64) : 0
      height: visible ? Style.space(64) : 0
      source: visible ? Model.fileUrl(row.info.image) : ""
      sourceSize.width: Style.space(128)
      fillMode: Image.PreserveAspectFit
      asynchronous: true
    }

    Column {
      width: content.width - (thumb.visible ? thumb.width + content.spacing : 0)
      spacing: Style.space(2)

      Item {
        width: parent.width
        height: title.implicitHeight

        Text {
          id: title
          width: parent.width - (sectionName.visible ? sectionName.implicitWidth + Style.space(8) : 0)
          text: row.info.title || ""
          textFormat: Text.PlainText
          elide: Text.ElideRight
          color: row.fg
          font.family: row.family
          font.pixelSize: Style.font.body
          font.bold: true
        }

        Text {
          id: sectionName
          anchors.right: parent.right
          anchors.verticalCenter: title.verticalCenter
          visible: row.showSection && row.entry !== null
          text: row.entry ? row.entry.section : ""
          textFormat: Text.PlainText
          color: row.dim
          font.family: row.family
          font.pixelSize: Style.font.caption
        }
      }

      Text {
        width: parent.width
        visible: text !== ""
        text: row.info.description || ""
        textFormat: Text.PlainText
        elide: Text.ElideRight
        color: row.dim
        font.family: row.family
        font.pixelSize: Style.font.caption
      }

      Repeater {
        model: row.preview.lines

        Text {
          required property var modelData
          width: parent.width
          text: modelData
          textFormat: Text.PlainText
          elide: Text.ElideRight
          color: row.fg
          opacity: 0.85
          font.family: row.family
          font.pixelSize: Style.font.bodySmall
        }
      }

      Text {
        visible: row.preview.more !== ""
        text: row.preview.more
        textFormat: Text.PlainText
        color: row.dim
        font.family: row.family
        font.pixelSize: Style.font.caption
      }

      Text {
        visible: row.info.missing === true
        text: "missing image"
        textFormat: Text.PlainText
        color: row.urgent
        font.family: row.family
        font.pixelSize: Style.font.caption
      }

      Flow {
        width: parent.width
        visible: row.chips.length > 0
        spacing: Style.space(4)

        Repeater {
          model: row.chips

          Rectangle {
            required property var modelData
            width: chipText.implicitWidth + Style.space(10)
            height: chipText.implicitHeight + Style.space(2)
            radius: height / 2
            opacity: modelData.inherited ? 0.6 : 1
            color: chipArea.containsMouse ? Style.hoverFillFor(row.fg, Color.accent)
              : Qt.rgba(row.fg.r, row.fg.g, row.fg.b, 0.08)

            Text {
              id: chipText
              anchors.centerIn: parent
              text: "#" + modelData.name
              textFormat: Text.PlainText
              color: row.fg
              font.family: row.family
              font.pixelSize: Style.font.caption
            }

            MouseArea {
              id: chipArea
              anchors.fill: parent
              hoverEnabled: true
              cursorShape: Qt.PointingHandCursor
              onClicked: row.tagClicked(modelData.name)
            }
          }
        }
      }
    }
  }
}
