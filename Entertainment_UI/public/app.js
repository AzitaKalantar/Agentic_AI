import React, { useEffect, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';

const h = React.createElement;
const SESSION_KEY = 'little-break-session';
const activities = [
  ['puzzle', '◇', 'A little challenge', 'One word. A few clues. Your move.', 'Give me a puzzle'],
  ['joke', '☺', 'Something funny', 'A fresh joke to lighten the day.', 'Tell me a joke'],
  ['fact', '✳', 'A curious discovery', 'Learn something delightfully unexpected.', 'Tell me a fun fact'],
  ['image', '❀', 'A dose of cute', 'Find your next favourite tiny creature.', 'Show me a cute baby animal'],
];
async function api(path, data) {
  const response = await fetch('/api/' + path, {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(data),
  });
  const result = await response.json();
  if (!response.ok) {
    const error = new Error(result.error || 'Something went wrong. Try again.');
    error.status = response.status;
    throw error;
  }
  return result;
}

function App() {
  const [session, setSession] = useState(null);
  const [mode, setMode] = useState('menu');
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState('');
  const lock = useRef(true);
  const bottom = useRef(null);
  const inputRef = useRef(null);
  useEffect(() => {
    let cancelled = false;
    async function restore() {
      try {
        const id = sessionStorage.getItem(SESSION_KEY);
        if (id) {
          const saved = await api('resume', {session_id: id});
          if (!cancelled) { setSession(id); setMode(saved.mode); setMessages(saved.messages); }
        }
      } catch (err) {
        if (err.status === 404) sessionStorage.removeItem(SESSION_KEY);
        else if (!cancelled) setError(err.message);
      } finally {
        if (!cancelled) { lock.current = false; setBusy(false); }
      }
    }
    restore();
    return () => { cancelled = true; };
  }, []);
  useEffect(() => {
    if (!session) return;
    let stream;
    function connect() {
      stream?.close();
      stream = new EventSource('/api/live?session_id=' + encodeURIComponent(session));
      stream.onmessage = event => {
        if (!lock.current) {
          const snapshot = JSON.parse(event.data);
          setMessages(previous => JSON.stringify(previous) === JSON.stringify(snapshot.messages) ? previous : snapshot.messages);
          setMode(snapshot.mode);
        }
      };
    }
    const disconnect = () => stream?.close();
    connect();
    window.addEventListener('pagehide', disconnect);
    window.addEventListener('pageshow', connect);
    return () => {
      disconnect();
      window.removeEventListener('pagehide', disconnect);
      window.removeEventListener('pageshow', connect);
    };
  }, [session]);
  useEffect(() => { bottom.current?.scrollIntoView({behavior: 'smooth', block: 'nearest'}); }, [messages, busy]);

  async function send(text) {
    text = text.trim();
    if (!text || lock.current || mode === 'closed') return;
    lock.current = true;
    setBusy(true); setError(''); setInput('');
    setMessages(previous => [...previous, {role: 'user', message: text}]);
    try {
      let id = session;
      if (!id) {
        id = (await api('session', {})).session_id;
        sessionStorage.setItem(SESSION_KEY, id);
        setSession(id);
      }
      const reply = await api('message', {session_id: id, message: text});
      setMode(reply.mode);
      setMessages(previous => [...previous, {...reply, role: 'assistant'}]);
    } catch (err) {
      if (err.status === 404) {
        sessionStorage.removeItem(SESSION_KEY); setSession(null); setMode('menu'); setMessages([]);
      }
      setError(err.message); setInput(text);
    }
    finally { lock.current = false; setBusy(false); setTimeout(() => inputRef.current?.focus(), 0); }
  }
  async function restart() {
    if (lock.current) return;
    lock.current = true; setBusy(true); setError('');
    try {
      if (session) {
        try { await api('end', {session_id: session}); }
        catch (err) { if (err.status !== 404) throw err; }
      }
      sessionStorage.removeItem(SESSION_KEY);
      setSession(null); setMode('menu'); setMessages([]); setInput('');
    } catch (err) { setError(err.message); }
    finally { lock.current = false; setBusy(false); }
  }
  return h('div', {className: 'shell'},
    h('header', {className: 'topbar'},
      h('a', {className: 'brand', href: '/'}, h('span', {className: 'brand-mark'}, '✳'), 'the little break'),
      h('span', {className: 'tag'}, 'YOUR ENTERTAINMENT PLAYGROUND'),
      h('button', {className: 'reset', onClick: restart, disabled: busy}, '↺ New conversation')),
    h('main', null,
      h('section', {className: 'intro'},
        h('div', {className: 'eyebrow'}, h('span', {className: 'dot'}), 'A SMALL PAUSE. A LITTLE JOY.'),
        h('h1', null, 'Make room for ', h('em', null, 'a little fun.')),
        h('p', null, 'A brain teaser, a good laugh, or something you never knew. What are you in the mood for?')),
      h('div', {className: 'workspace'},
        h('aside', {className: 'activities'},
          h('div', {className: 'section-label'}, 'PICK YOUR LITTLE BREAK'),
          ...activities.map(([key, icon, title, description, prompt]) => h('button', {
            key, className: 'activity ' + key, disabled: busy || mode !== 'menu', onClick: () => send(prompt),
          }, h('span', {className: 'activity-icon'}, icon),
          h('span', {className: 'activity-copy'}, h('strong', null, title), h('small', null, description)),
          h('span', {className: 'arrow'}, '↗'))),
          h('button', {className: 'surprise', disabled: busy || mode !== 'menu', onClick: () => send('Surprise me')}, '✧  Surprise me', h('span', null, 'Let chance choose →')),
          h('p', {className: 'aside-note'}, mode === 'puzzle' ? 'A puzzle is in progress. Make a guess, ask for a hint, or return to the menu.' : 'You can also ask in your own words. Your host will take it from there.')),
        h('section', {className: 'chat', 'aria-label': 'Conversation'},
          h('div', {className: 'chat-header'},
            h('div', {className: 'host'}, h('span', {className: 'avatar'}, '✳'), h('div', null, h('strong', null, 'Your break companion'), h('small', null, 'A little curiosity goes a long way'))),
            h('span', {className: 'status'}, mode === 'puzzle' ? 'Puzzle in play' : mode === 'closed' ? 'Ended' : 'Ready to play')),
          h('div', {className: 'messages', role: 'log', 'aria-live': 'polite'},
            messages.length === 0 && h('div', {className: 'welcome'}, h('div', {className: 'welcome-icon'}, '✧'), h('h2', null, 'Hello, curious human.'), h('p', null, 'Pick something on the left, or tell me what would make your day a little brighter.'), h('span', null, 'Your next little adventure starts here.')),
            ...messages.map((item, index) => h('article', {key: index, className: 'message ' + item.role},
              h('span', {className: 'message-label'}, item.role === 'user' ? 'YOU' : item.action === 'chat' ? 'YOUR HOST' : (item.action || 'HOST').toUpperCase()),
              h('p', null, item.message),
              item.image && h('figure', null, h('img', {src: item.image.image_url, alt: item.image.title, loading: 'lazy', onError: event => { event.currentTarget.hidden = true; }}), h('figcaption', null, h('a', {href: item.image.source_url, target: '_blank', rel: 'noopener noreferrer'}, 'View source & license ↗'))),
              item.puzzle_status && h('small', {className: 'puzzle-status'}, {playing: 'Your turn — guess or ask for a hint', solved: 'Nicely done! Puzzle solved.', revealed: 'Answer revealed. Ready for another?'}[item.puzzle_status]))),
            busy && h('div', {className: 'thinking', role: 'status'}, '✳  Finding a little joy for you…'),
            h('div', {ref: bottom})),
          error && h('div', {className: 'error', role: 'alert'}, error),
          mode === 'puzzle' && h('div', {className: 'puzzle-controls'}, ...[['Hint', 'Give me a hint'], ['Reveal answer', 'Tell me the answer'], ['Back to menu', 'menu']].map(([label, text]) => h('button', {key: label, disabled: busy, onClick: () => send(text)}, label))),
          mode === 'closed' ? h('div', {className: 'closed'}, 'Thanks for taking a little break. ', h('button', {onClick: restart, disabled: busy}, 'Start again →')) :
          h('form', {className: 'composer', onSubmit: event => { event.preventDefault(); send(input); }},
            h('input', {ref: inputRef, value: input, onChange: event => setInput(event.target.value), maxLength: 4000, disabled: busy, 'aria-label': 'Message your entertainment host', placeholder: mode === 'puzzle' ? 'Your guess, or ask for a hint…' : 'Tell me a joke, show me a kitten…'}),
            h('button', {type: 'submit', disabled: busy || !input.trim(), 'aria-label': 'Send message'}, '↑')),
          h('div', {className: 'chat-footnote'}, 'Powered by your entertainment agents · Responses may take a moment')))),
    h('footer', null, h('span', null, 'MADE FOR THE MOMENTS IN BETWEEN'), h('span', null, 'Stay curious. Take a break.')));
}
createRoot(document.getElementById('root')).render(h(App));
