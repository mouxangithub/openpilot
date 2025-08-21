#include "selfdrive/ui/qt/widgets/ssh_keys.h"

#include "common/params.h"
#include "selfdrive/ui/qt/api.h"
#include "selfdrive/ui/qt/widgets/input.h"

SshControl::SshControl() :
  ButtonControl(tr("SSH密钥"), "", tr("警告：这将授予对您GitHub设置中所有公钥的SSH访问权限。请勿输入除您自己之外的GitHub用户名。"
                                       "Comma员工绝不会要求您添加他们的GitHub用户名。")) {

  QObject::connect(this, &ButtonControl::clicked, [=]() {
    if (text() == tr("添加")) {
      QString username = InputDialog::getText(tr("输入您的GitHub用户名"), this);
      if (username.length() > 0) {
        setText(tr("加载中"));
        setEnabled(false);
        getUserKeys(username);
      }
    } else {
      params.remove("GithubUsername");
      params.remove("GithubSshKeys");
      refresh();
    }
  });

  refresh();
}

void SshControl::refresh() {
  QString param = QString::fromStdString(params.get("GithubSshKeys"));
  if (param.length()) {
    setValue(QString::fromStdString(params.get("GithubUsername")));
    setText(tr("移除"));
  } else {
    setValue("");
    setText(tr("添加"));
  }
  setEnabled(true);
}

void SshControl::getUserKeys(const QString &username) {
  HttpRequest *request = new HttpRequest(this, false);
  QObject::connect(request, &HttpRequest::requestDone, [=](const QString &resp, bool success) {
    if (success) {
      if (!resp.isEmpty()) {
        params.put("GithubUsername", username.toStdString());
        params.put("GithubSshKeys", resp.toStdString());
      } else {
        ConfirmationDialog::alert(tr("用户名 '%1' 在GitHub上没有密钥").arg(username), this);
      }
    } else {
      if (request->timeout()) {
        ConfirmationDialog::alert(tr("请求超时"), this);
      } else {
        ConfirmationDialog::alert(tr("用户名 '%1' 在GitHub上不存在").arg(username), this);
      }
    }

    refresh();
    request->deleteLater();
  });

  request->sendRequest("https://github.com/" + username + ".keys");
}
