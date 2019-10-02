import { promises as fs } from 'fs'
import * as path from 'path'
import * as http from 'http'
import * as WebSocket from 'ws'
import * as Koa from 'koa'
import * as Router from '@koa/router'
import * as fns from 'date-fns'
import * as koaBody from 'koa-body'
import * as multer from '@koa/multer'


const API_PORT = 8080
const WS_PORT = 8081
const UPLOAD_DIR = 'uploaded/'

const wss = new WebSocket.Server({ port: WS_PORT })
const app = new Koa()
const router = new Router()
const upload = multer()


class Status {
  private current: string
  constructor() {
    this.current = null
  }
  to_json(): string {
    return JSON.stringify({
      current: this.current,
    })
  }
}

function generate_id(): string {
  return fns.format(new Date(), 'yyyy-MM-dd_HHmmss')
}

function get_path(id: string): string {
 return path.join(UPLOAD_DIR, id + '.jpg')
}

const status = new Status()

wss.on('connection', (ws: WebSocket, socket: WebSocket, request: http.IncomingMessage) => {
  ws.on('message', (message: string) => {
    // console.log('received: %s', message)
    ws.send(status.to_json())
  })
})

router.get('/images', async (ctx: Koa.Context, next) => {
  console.log('get images')
  ctx.body = 'images'
})

router.post(
  '/upload',
  upload.single('image'),
  async (ctx: Koa.Context, next) => {
    console.log('ctx.file', ctx.file)
    console.log(ctx.file.buffer)
    const i = generate_id()
    const p = get_path(i)
    await fs.writeFile(p, ctx.file.buffer)
    ctx.body = 'up'
    console.log('wrote: ', p)
  }
)

app.use(router.routes())
app.use(router.allowedMethods())
app.use(koaBody({ multipart: true }))
app.listen(API_PORT, () => {
    console.log('Started')
})
