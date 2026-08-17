import { DatabaseSync } from 'node:sqlite';
import crypto from 'node:crypto';

const db = new DatabaseSync(new URL('./data.db', import.meta.url));

const email = 'team@epochx.local';
const password = 'Test1234!';

function hashPassword(password) {
  const salt = crypto.randomBytes(16).toString('hex');
  const hash = crypto.scryptSync(password, salt, 64).toString('hex');
  return `${salt}:${hash}`;
}

db.prepare(`
  INSERT INTO users (email, password_hash, created_at) VALUES (?, ?, ?)
  ON CONFLICT(email) DO UPDATE SET password_hash = excluded.password_hash
`).run(email, hashPassword(password), new Date().toISOString());

console.log(`测试账号已就绪：${email} / ${password}`);
