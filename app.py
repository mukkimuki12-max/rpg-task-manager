import random
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)
app.secret_key = 'rpg-task-manager-2024'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///rpg.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)


# ========== Models ==========

class Avatar(db.Model):
    __tablename__ = 'avatars'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), default='勇者')
    base_hp = db.Column(db.Integer, default=100)
    base_attack = db.Column(db.Integer, default=10)
    base_defense = db.Column(db.Integer, default=5)
    base_agility = db.Column(db.Integer, default=8)
    points = db.Column(db.Integer, default=0)
    total_points_earned = db.Column(db.Integer, default=0)
    inventory = db.relationship('Inventory', back_populates='avatar', lazy='dynamic')

    @property
    def equipped_items(self):
        return [inv.item for inv in self.inventory.filter_by(is_equipped=True).all()]

    @property
    def total_hp(self):
        return self.base_hp + sum(item.hp_bonus for item in self.equipped_items)

    @property
    def total_attack(self):
        return self.base_attack + sum(item.attack_bonus for item in self.equipped_items)

    @property
    def total_defense(self):
        return self.base_defense + sum(item.defense_bonus for item in self.equipped_items)

    @property
    def total_agility(self):
        return self.base_agility + sum(item.agility_bonus for item in self.equipped_items)

    @property
    def level(self):
        return self.total_points_earned // 10 + 1

    @property
    def level_progress(self):
        return self.total_points_earned % 10


class Task(db.Model):
    __tablename__ = 'tasks'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, default='')
    status = db.Column(db.String(20), default='not_started')
    priority = db.Column(db.Integer, default=0)
    points_earned = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime, nullable=True)

    STATUS_LABELS = {
        'not_started': '未着手',
        'in_progress': '実行中',
        'withdrawn': '取り下げ',
        'completed': '完了',
    }

    @property
    def status_label(self):
        return self.STATUS_LABELS.get(self.status, self.status)


class ShopItem(db.Model):
    __tablename__ = 'shop_items'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    item_type = db.Column(db.String(20), nullable=False)
    price = db.Column(db.Integer, nullable=False)
    hp_bonus = db.Column(db.Integer, default=0)
    attack_bonus = db.Column(db.Integer, default=0)
    defense_bonus = db.Column(db.Integer, default=0)
    agility_bonus = db.Column(db.Integer, default=0)
    emoji = db.Column(db.String(10), default='📦')
    rarity = db.Column(db.String(20), default='common')

    TYPE_LABELS = {
        'helmet': '兜',
        'weapon': '武器',
        'armor': '鎧',
        'shield': '盾',
        'boots': '靴',
    }

    @property
    def type_label(self):
        return self.TYPE_LABELS.get(self.item_type, self.item_type)

    @property
    def stat_summary(self):
        parts = []
        if self.hp_bonus > 0:
            parts.append(f'HP+{self.hp_bonus}')
        if self.attack_bonus > 0:
            parts.append(f'ATK+{self.attack_bonus}')
        if self.defense_bonus > 0:
            parts.append(f'DEF+{self.defense_bonus}')
        if self.agility_bonus != 0:
            sign = '+' if self.agility_bonus > 0 else ''
            parts.append(f'AGI{sign}{self.agility_bonus}')
        return ' / '.join(parts) if parts else 'ボーナスなし'


class Inventory(db.Model):
    __tablename__ = 'inventory'
    id = db.Column(db.Integer, primary_key=True)
    avatar_id = db.Column(db.Integer, db.ForeignKey('avatars.id'), nullable=False)
    shop_item_id = db.Column(db.Integer, db.ForeignKey('shop_items.id'), nullable=False)
    is_equipped = db.Column(db.Boolean, default=False)
    acquired_at = db.Column(db.DateTime, default=datetime.utcnow)

    avatar = db.relationship('Avatar', back_populates='inventory')
    item = db.relationship('ShopItem')


# ========== Shop Item Definitions ==========

SHOP_ITEMS_DATA = [
    # Helmets
    {'name': '革の帽子',    'type': 'helmet', 'emoji': '🪖', 'rarity': 'common',
     'hp': (3, 8),   'atk': (0, 0),   'def': (1, 4),   'agi': (0, 2)},
    {'name': '鉄の兜',      'type': 'helmet', 'emoji': '⛑', 'rarity': 'rare',
     'hp': (8, 15),  'atk': (0, 0),   'def': (4, 8),   'agi': (-2, 0)},
    {'name': '魔法の王冠',  'type': 'helmet', 'emoji': '👑', 'rarity': 'epic',
     'hp': (10, 20), 'atk': (3, 8),   'def': (2, 6),   'agi': (1, 4)},
    # Weapons
    {'name': '木の剣',      'type': 'weapon', 'emoji': '🗡', 'rarity': 'common',
     'hp': (0, 0),   'atk': (3, 8),   'def': (0, 0),   'agi': (0, 2)},
    {'name': '鉄の剣',      'type': 'weapon', 'emoji': '⚔', 'rarity': 'rare',
     'hp': (0, 0),   'atk': (8, 15),  'def': (0, 2),   'agi': (-1, 1)},
    {'name': '魔法の杖',    'type': 'weapon', 'emoji': '🪄', 'rarity': 'epic',
     'hp': (3, 8),   'atk': (15, 25), 'def': (0, 0),   'agi': (2, 5)},
    # Armor
    {'name': '革の鎧',      'type': 'armor',  'emoji': '🥋', 'rarity': 'common',
     'hp': (8, 15),  'atk': (0, 0),   'def': (3, 8),   'agi': (0, 3)},
    {'name': '鉄の鎧',      'type': 'armor',  'emoji': '🛡', 'rarity': 'rare',
     'hp': (15, 25), 'atk': (0, 0),   'def': (10, 18), 'agi': (-3, -1)},
    {'name': '魔法のローブ', 'type': 'armor',  'emoji': '👘', 'rarity': 'epic',
     'hp': (20, 35), 'atk': (5, 12),  'def': (5, 12),  'agi': (3, 8)},
    # Shields
    {'name': '木の盾',      'type': 'shield', 'emoji': '🪵', 'rarity': 'common',
     'hp': (3, 8),   'atk': (0, 0),   'def': (3, 8),   'agi': (-1, 1)},
    {'name': '鉄の盾',      'type': 'shield', 'emoji': '🔰', 'rarity': 'rare',
     'hp': (0, 5),   'atk': (0, 0),   'def': (8, 15),  'agi': (-2, 0)},
    # Boots
    {'name': '革のブーツ',    'type': 'boots', 'emoji': '👟', 'rarity': 'common',
     'hp': (3, 8),   'atk': (0, 0),   'def': (0, 2),   'agi': (3, 8)},
    {'name': '魔法のサンダル', 'type': 'boots', 'emoji': '🥿', 'rarity': 'epic',
     'hp': (8, 15),  'atk': (1, 4),   'def': (0, 3),   'agi': (8, 15)},
]

RARITY_PRICE = {
    'common': (10, 35),
    'rare':   (36, 70),
    'epic':   (71, 100),
}


def init_db():
    db.create_all()

    # マイグレーション: priority カラムが存在しない場合に追加
    with db.engine.connect() as conn:
        try:
            conn.execute(db.text('ALTER TABLE tasks ADD COLUMN priority INTEGER DEFAULT 0'))
            conn.commit()
        except Exception:
            pass  # すでに存在する

    if not Avatar.query.first():
        db.session.add(Avatar(name='勇者'))

    if not ShopItem.query.first():
        for data in SHOP_ITEMS_DATA:
            price_range = RARITY_PRICE[data['rarity']]
            item = ShopItem(
                name=data['name'],
                item_type=data['type'],
                emoji=data['emoji'],
                rarity=data['rarity'],
                price=random.randint(*price_range),
                hp_bonus=random.randint(*data['hp']),
                attack_bonus=random.randint(*data['atk']),
                defense_bonus=random.randint(*data['def']),
                agility_bonus=random.randint(*data['agi']),
            )
            db.session.add(item)

    db.session.commit()


# ========== Routes ==========

@app.route('/')
def index():
    avatar = Avatar.query.first()
    tasks_by_status = {
        s: Task.query.filter_by(status=s).order_by(Task.priority).all()
        for s in ['not_started', 'in_progress', 'withdrawn', 'completed']
    }
    return render_template('tasks.html', tasks_by_status=tasks_by_status, avatar=avatar)


@app.route('/tasks/add', methods=['POST'])
def add_task():
    title = request.form.get('title', '').strip()
    description = request.form.get('description', '').strip()
    if not title:
        return jsonify({'error': 'タスク名を入力してください'}), 400
    max_p = db.session.query(db.func.max(Task.priority)).filter_by(status='not_started').scalar()
    task = Task(title=title, description=description, priority=(max_p or 0) + 1)
    db.session.add(task)
    db.session.commit()
    return jsonify({
        'id': task.id,
        'title': task.title,
        'description': task.description or '',
        'created_at': task.created_at.strftime('%Y/%m/%d %H:%M'),
    })


@app.route('/tasks/delete/<int:task_id>', methods=['POST'])
def delete_task(task_id):
    task = db.session.get(Task, task_id)
    if not task:
        return jsonify({'error': 'not found'}), 404
    db.session.delete(task)
    db.session.commit()
    return jsonify({'success': True})


@app.route('/tasks/update_status/<int:task_id>', methods=['POST'])
def update_task_status(task_id):
    task = db.session.get(Task, task_id)
    if not task:
        flash('タスクが見つかりません。', 'error')
        return redirect(url_for('index'))

    new_status = request.form.get('status')
    if new_status not in ['not_started', 'in_progress', 'withdrawn', 'completed']:
        flash('無効なステータスです。', 'error')
        return redirect(url_for('index'))

    old_status = task.status
    task.status = new_status

    if new_status == 'completed' and old_status != 'completed':
        points = random.randint(1, 5)
        task.points_earned = points
        task.completed_at = datetime.utcnow()
        avatar = Avatar.query.first()
        avatar.points += points
        avatar.total_points_earned += points
        db.session.commit()
        flash(f'タスク「{task.title}」を完了！ {points}ポイント獲得！', 'success')
    else:
        db.session.commit()
        flash(f'ステータスを「{task.status_label}」に変更しました。', 'info')

    return redirect(url_for('index'))


@app.route('/tasks/reorder', methods=['POST'])
def reorder_tasks():
    data = request.get_json()
    task_id = int(data['task_id'])
    new_status = data['new_status']
    column_order = [int(x) for x in data['column_order']]

    if new_status not in ['not_started', 'in_progress', 'withdrawn', 'completed']:
        return jsonify({'error': 'invalid status'}), 400

    task = db.session.get(Task, task_id)
    if not task:
        return jsonify({'error': 'not found'}), 404

    old_status = task.status
    task.status = new_status

    points_earned = None
    total_points = None
    if new_status == 'completed' and old_status != 'completed' and task.points_earned == 0:
        pts = random.randint(1, 5)
        task.points_earned = pts
        task.completed_at = datetime.utcnow()
        avatar = Avatar.query.first()
        avatar.points += pts
        avatar.total_points_earned += pts
        points_earned = pts
        total_points = avatar.points

    for i, tid in enumerate(column_order):
        t = db.session.get(Task, tid)
        if t:
            t.priority = i

    db.session.commit()

    resp = {'success': True}
    if points_earned is not None:
        resp['points'] = points_earned
        resp['total_points'] = total_points
    return jsonify(resp)


@app.route('/mypage')
def mypage():
    avatar = Avatar.query.first()
    inventory_items = Inventory.query.filter_by(avatar_id=avatar.id).all()
    shop_items = ShopItem.query.order_by(ShopItem.item_type, ShopItem.price).all()
    owned_item_ids = {inv.shop_item_id for inv in inventory_items}

    equipped_by_type = {}
    for inv in inventory_items:
        if inv.is_equipped:
            equipped_by_type[inv.item.item_type] = inv

    return render_template('mypage.html',
                           avatar=avatar,
                           inventory_items=inventory_items,
                           shop_items=shop_items,
                           owned_item_ids=owned_item_ids,
                           equipped_by_type=equipped_by_type)


@app.route('/shop/buy/<int:item_id>', methods=['POST'])
def buy_item(item_id):
    item = db.session.get(ShopItem, item_id)
    if not item:
        flash('アイテムが見つかりません。', 'error')
        return redirect(url_for('mypage'))

    avatar = Avatar.query.first()
    if Inventory.query.filter_by(avatar_id=avatar.id, shop_item_id=item_id).first():
        flash('すでに所持しているアイテムです。', 'warning')
        return redirect(url_for('mypage'))

    if avatar.points < item.price:
        flash(f'ポイントが足りません。（必要: {item.price}pt / 所持: {avatar.points}pt）', 'error')
        return redirect(url_for('mypage'))

    avatar.points -= item.price
    db.session.add(Inventory(avatar_id=avatar.id, shop_item_id=item_id))
    db.session.commit()
    flash(f'「{item.name}」を購入しました！', 'success')
    return redirect(url_for('mypage'))


@app.route('/avatar/equip/<int:inv_id>', methods=['POST'])
def equip_item(inv_id):
    inv = db.session.get(Inventory, inv_id)
    if not inv:
        return redirect(url_for('mypage'))

    avatar = Avatar.query.first()
    for other in Inventory.query.filter_by(avatar_id=avatar.id, is_equipped=True).all():
        if other.item.item_type == inv.item.item_type:
            other.is_equipped = False

    inv.is_equipped = True
    db.session.commit()
    flash(f'「{inv.item.name}」を装備しました！', 'success')
    return redirect(url_for('mypage'))


@app.route('/avatar/unequip/<int:inv_id>', methods=['POST'])
def unequip_item(inv_id):
    inv = db.session.get(Inventory, inv_id)
    if not inv:
        return redirect(url_for('mypage'))
    inv.is_equipped = False
    db.session.commit()
    flash(f'「{inv.item.name}」を外しました。', 'info')
    return redirect(url_for('mypage'))


if __name__ == '__main__':
    with app.app_context():
        init_db()
    app.run(debug=True, port=5000)
