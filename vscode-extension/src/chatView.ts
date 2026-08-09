import * as vscode from "vscode";

export type ChatMessage =
  | { type: "chat"; text: string; model?: string }
  | { type: "cancel" }
  | { type: "openOutput" }
  | { type: "apply"; transactionId: string; files?: string[] }
  | { type: "reject"; transactionId: string; files?: string[] }
  | { type: "preview"; transactionId: string; file?: string };

export class ChatViewProvider implements vscode.WebviewViewProvider {
  private view?: vscode.WebviewView;
  private readonly incoming = new vscode.EventEmitter<ChatMessage>();
  readonly onMessage = this.incoming.event;

  constructor(
    private readonly extensionUri: vscode.Uri,
    private readonly persisted: () => unknown,
  ) {}

  resolveWebviewView(view: vscode.WebviewView): void {
    this.view = view;
    view.webview.options = {
      enableScripts: true,
      localResourceRoots: [this.extensionUri],
    };
    view.webview.html = html(view.webview, this.persisted());
    view.webview.onDidReceiveMessage((message: ChatMessage) => this.incoming.fire(message));
  }

  post(type: string, payload: Record<string, unknown> = {}): void {
    void this.view?.webview.postMessage({ type, ...payload });
  }

  dispose(): void {
    this.incoming.dispose();
  }
}

function html(webview: vscode.Webview, state: unknown): string {
  const nonce = Math.random().toString(36).slice(2);
  const initial = JSON.stringify(state ?? {}).replace(/</g, "\\u003c");
  return `<!doctype html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src ${webview.cspSource} 'unsafe-inline'; script-src 'nonce-${nonce}'">
  <style>
    body { padding: 0; color: var(--vscode-foreground); font: var(--vscode-font-size)/1.45 var(--vscode-font-family); }
    header { display:flex; gap:6px; align-items:center; padding:8px; border-bottom:1px solid var(--vscode-panel-border); }
    #status { margin-left:auto; font-size:11px; opacity:.8; }
    #messages { padding:8px; overflow-wrap:anywhere; }
    .message { margin:8px 0; padding:8px; border-radius:5px; white-space:pre-wrap; }
    .user { background:var(--vscode-input-background); }
    .assistant { border-left:2px solid var(--vscode-focusBorder); }
    .error { color:var(--vscode-errorForeground); }
    .proposal { border:1px solid var(--vscode-panel-border); padding:8px; margin:8px 0; }
    footer { position:sticky; bottom:0; padding:8px; background:var(--vscode-sideBar-background); }
    textarea { box-sizing:border-box; width:100%; min-height:74px; resize:vertical; color:var(--vscode-input-foreground); background:var(--vscode-input-background); border:1px solid var(--vscode-input-border); }
    button, select { color:var(--vscode-button-foreground); background:var(--vscode-button-background); border:0; padding:5px 8px; }
    button.secondary { color:var(--vscode-foreground); background:var(--vscode-button-secondaryBackground); }
    .actions { display:flex; gap:6px; margin-top:6px; }
  </style>
</head>
<body>
  <header>
    <select id="model" aria-label="Model"></select>
    <button id="output" class="secondary">Output</button>
    <span id="status">stopped</span>
  </header>
  <main id="messages"></main>
  <footer>
    <textarea id="prompt" placeholder="Ask Eurika… Use @file:path or @folder:path"></textarea>
    <div class="actions"><button id="send">Send</button><button id="cancel" class="secondary">Cancel</button></div>
  </footer>
  <script nonce="${nonce}">
    const vscode = acquireVsCodeApi();
    const initial = ${initial};
    const messages = document.getElementById('messages');
    const prompt = document.getElementById('prompt');
    const model = document.getElementById('model');
    let history = initial.messages || [];
    let streaming;
    function add(role, text, save=true) {
      const el = document.createElement('div');
      el.className = 'message ' + role;
      el.textContent = text;
      messages.appendChild(el);
      if (save) { history.push({role,text}); vscode.setState({messages:history}); }
      return el;
    }
    history.forEach(item => add(item.role, item.text, false));
    document.getElementById('send').onclick = () => {
      const text = prompt.value.trim(); if (!text) return;
      add('user', text); prompt.value = '';
      vscode.postMessage({type:'chat', text, model:model.value});
    };
    prompt.onkeydown = event => {
      if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); document.getElementById('send').click(); }
    };
    document.getElementById('cancel').onclick = () => vscode.postMessage({type:'cancel'});
    document.getElementById('output').onclick = () => vscode.postMessage({type:'openOutput'});
    window.addEventListener('message', ({data}) => {
      if (data.type === 'status') document.getElementById('status').textContent = data.status;
      if (data.type === 'models') {
        model.replaceChildren(...data.models.map(item => {
          const option = document.createElement('option');
          option.value = typeof item === 'string' ? item : item.id;
          option.textContent = typeof item === 'string' ? item : (item.label || item.id);
          return option;
        }));
        if (data.selected) model.value = data.selected;
      }
      if (data.type === 'streamStart') streaming = add('assistant', '', false);
      if (data.type === 'stream') {
        if (!streaming) streaming = add('assistant', '', false);
        streaming.textContent += data.text;
      }
      if (data.type === 'streamEnd' && streaming) {
        history.push({role:'assistant', text:streaming.textContent});
        vscode.setState({messages:history}); streaming = undefined;
      }
      if (data.type === 'error') add('error', data.message);
      if (data.type === 'proposal') {
        const box = document.createElement('div'); box.className = 'proposal'; box.dataset.transactionId=data.transactionId;
        const title = document.createElement('div'); title.textContent = 'Proposed changes: ' + data.files.length + ' file(s)'; box.appendChild(title);
        const checks = [];
        data.files.forEach(file => {
          const row = document.createElement('div'); row.dataset.file=file;
          const check = document.createElement('input'); check.type='checkbox'; check.checked=true; check.value=file; checks.push(check);
          const button = document.createElement('button'); button.className='secondary'; button.textContent=file; button.onclick=()=>vscode.postMessage({type:'preview',transactionId:data.transactionId,file});
          row.append(check,button); box.appendChild(row);
        });
        const selected = () => checks.filter(check => check.checked).map(check => check.value);
        const actions = document.createElement('div'); actions.className='actions';
        const apply=document.createElement('button'); apply.textContent='Apply selected'; apply.onclick=()=>vscode.postMessage({type:'apply',transactionId:data.transactionId,files:selected()});
        const reject=document.createElement('button'); reject.className='secondary'; reject.textContent='Reject selected'; reject.onclick=()=>vscode.postMessage({type:'reject',transactionId:data.transactionId,files:selected()});
        actions.append(apply,reject); box.appendChild(actions); messages.appendChild(box);
      }
      if (data.type === 'proposalUpdate') {
        const box = [...document.querySelectorAll('.proposal')].find(item => item.dataset.transactionId === data.transactionId);
        if (box) {
          [...box.querySelectorAll('[data-file]')].forEach(row => {
            if (!data.files.includes(row.dataset.file)) row.remove();
          });
          if (!data.files.length) box.remove();
        }
      }
    });
  </script>
</body>
</html>`;
}
