const fs =  require('fs').promises
const pathlib = require('path')
const util = require('util')
const childProcess = require('child_process')
// const http = require('http')
const WebSocket = require('ws')
const Koa = require('koa')
const Router = require('@koa/router')
const fns = require('date-fns')
const koaBody = require('koa-body')
const multer = require('@koa/multer')

const exec = util.promisify(childProcess.exec)



const API_PORT = 8080
const WS_PORT = 8081
const UPLOAD_DIR = 'uploaded/'
const GENERATED_DIR = 'generated/'

const wss = new WebSocket.Server({ port: WS_PORT })
const app = new Koa()
const router = new Router()
const upload = multer()

function generate_id() {
  return fns.format(new Date(), 'yyyy-MM-dd_HHmmss')
}

function get_uploaded_path(id) {
 return pathlib.join(UPLOAD_DIR, id + '.jpg')
}

function get_generated_dir(id) {
 return pathlib.join(GENERATED_DIR, id + '.jpg')
}

async function do_inference(id) {
  await exec(`bash scripts/fake.sh ${id}.jpg`)
}

function wait(s) {
  return new Promise(function (r) {
    setTimeout(r, s)
  })
}

class App {
  constructor() {
    this.items = []
    this.queue = new Promise()
  }
  to_json() {
    return JSON.stringify({
      items: this.items,
    })
  }
  push_task(id) {
    this.items.push(id)
    this.queue = this.queue.catch(function(e) {
      console.log(`ERROR: ${e}`)
    }).then(async () => {
      await do_inference(this.items.shift())
      await wait(3)
    })
    console.log('CUR: ', this.items)
  }
}



const app = new App()

wss.on('connection', (ws, socket, request) => {
  ws.on('message', (message) => {
    // console.log('received: %s', message)
    ws.send(app.to_json())
  })
})

router.get('/images', async (ctx, next) => {
  console.log('get images')
  ctx.body = 'images'
})

router.post(
  '/upload',
  upload.single('image'),
  async (ctx, next) => {
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
