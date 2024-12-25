import os
from datetime import datetime
from flask import Flask, render_template, url_for, flash, redirect, request, abort, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, current_user, logout_user, login_required
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-here'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///blog.db'
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Create uploads directory if it doesn't exist
os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'images'), exist_ok=True)
os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'audio'), exist_ok=True)

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Lütfen giriş yapın.'
login_manager.login_message_category = 'info'

# Association table for post tags
post_tags = db.Table('post_tags',
    db.Column('post_id', db.Integer, db.ForeignKey('post.id'), primary_key=True),
    db.Column('tag_id', db.Integer, db.ForeignKey('tag.id'), primary_key=True)
)

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=True)
    password_hash = db.Column(db.String(128))
    profile_pic = db.Column(db.String(120), nullable=True)
    bio = db.Column(db.Text, nullable=True)
    posts = db.relationship('Post', backref='author', lazy=True)
    comments = db.relationship('Comment', backref='author', lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    posts = db.relationship('Post', backref='category', lazy=True)

class Tag(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)

class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    content = db.Column(db.Text, nullable=False)
    date_posted = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey('category.id'), nullable=True)
    image_file = db.Column(db.String(120), nullable=True)
    audio_file = db.Column(db.String(120), nullable=True)
    comments = db.relationship('Comment', backref='post', lazy=True, cascade='all, delete-orphan')
    tags = db.relationship('Tag', secondary=post_tags, lazy='subquery',
                          backref=db.backref('posts', lazy=True))

class Comment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    date_posted = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey('post.id'), nullable=False)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

def save_picture(file, folder):
    if file:
        filename = secure_filename(file.filename)
        unique_filename = f"{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{filename}"
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], folder, unique_filename))
        return unique_filename
    return None

@app.route('/')
@app.route('/home')
def home():
    page = request.args.get('page', 1, type=int)
    posts = Post.query.order_by(Post.date_posted.desc()).paginate(page=page, per_page=5)
    categories = Category.query.all()
    tags = Tag.query.all()
    return render_template('home.html', posts=posts, categories=categories, tags=tags)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('home'))
    if request.method == 'POST':
        user = User(username=request.form['username'])
        user.set_password(request.form['password'])
        db.session.add(user)
        try:
            db.session.commit()
            flash('Hesabınız başarıyla oluşturuldu!', 'success')
            return redirect(url_for('login'))
        except:
            db.session.rollback()
            flash('Bu kullanıcı adı zaten kullanılıyor.', 'danger')
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('home'))
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form['username']).first()
        if user and user.check_password(request.form['password']):
            login_user(user)
            next_page = request.args.get('next')
            return redirect(next_page) if next_page else redirect(url_for('home'))
        flash('Kullanıcı adı veya şifre hatalı.', 'danger')
    return render_template('login.html')

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('home'))

@app.route('/profile/<string:username>')
def profile(username):
    user = User.query.filter_by(username=username).first_or_404()
    page = request.args.get('page', 1, type=int)
    posts = Post.query.filter_by(author=user).order_by(Post.date_posted.desc()).paginate(page=page, per_page=5)
    return render_template('profile.html', user=user, posts=posts)

@app.route('/profile/edit', methods=['GET', 'POST'])
@login_required
def edit_profile():
    if request.method == 'POST':
        if 'profile_pic' in request.files:
            file = request.files['profile_pic']
            if file.filename:
                filename = save_picture(file, 'images')
                if filename:
                    current_user.profile_pic = filename
        
        current_user.email = request.form['email']
        current_user.bio = request.form['bio']
        
        try:
            db.session.commit()
            flash('Profiliniz güncellendi!', 'success')
            return redirect(url_for('profile', username=current_user.username))
        except:
            db.session.rollback()
            flash('Bir hata oluştu.', 'danger')
    
    return render_template('edit_profile.html')

@app.route('/post/new', methods=['GET', 'POST'])
@login_required
def new_post():
    categories = Category.query.all()
    tags = Tag.query.all()
    if request.method == 'POST':
        image_file = None
        audio_file = None
        
        if 'image' in request.files:
            image = request.files['image']
            if image.filename:
                image_file = save_picture(image, 'images')
        
        if 'audio' in request.files:
            audio = request.files['audio']
            if audio.filename:
                audio_file = save_picture(audio, 'audio')
        
        post = Post(
            title=request.form['title'],
            content=request.form['content'],
            author=current_user,
            image_file=image_file,
            audio_file=audio_file
        )
        
        if request.form.get('category'):
            category = Category.query.get(int(request.form['category']))
            if category:
                post.category = category
        
        tag_ids = request.form.getlist('tags')
        for tag_id in tag_ids:
            tag = Tag.query.get(int(tag_id))
            if tag:
                post.tags.append(tag)
        
        db.session.add(post)
        try:
            db.session.commit()
            flash('Yazınız başarıyla oluşturuldu!', 'success')
            return redirect(url_for('post', post_id=post.id))
        except:
            db.session.rollback()
            flash('Bir hata oluştu.', 'danger')
    
    return render_template('create_post.html', categories=categories, tags=tags)

@app.route('/post/<int:post_id>')
def post(post_id):
    post = Post.query.get_or_404(post_id)
    return render_template('post.html', post=post)

@app.route('/post/<int:post_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_post(post_id):
    post = Post.query.get_or_404(post_id)
    if post.author != current_user:
        abort(403)
    
    categories = Category.query.all()
    tags = Tag.query.all()
    
    if request.method == 'POST':
        if 'image' in request.files:
            image = request.files['image']
            if image.filename:
                image_file = save_picture(image, 'images')
                post.image_file = image_file
        
        if 'audio' in request.files:
            audio = request.files['audio']
            if audio.filename:
                audio_file = save_picture(audio, 'audio')
                post.audio_file = audio_file
        
        post.title = request.form['title']
        post.content = request.form['content']
        
        if request.form.get('category'):
            category = Category.query.get(int(request.form['category']))
            if category:
                post.category = category
        else:
            post.category = None
        
        post.tags.clear()
        tag_ids = request.form.getlist('tags')
        for tag_id in tag_ids:
            tag = Tag.query.get(int(tag_id))
            if tag:
                post.tags.append(tag)
        
        try:
            db.session.commit()
            flash('Yazınız güncellendi!', 'success')
            return redirect(url_for('post', post_id=post.id))
        except:
            db.session.rollback()
            flash('Bir hata oluştu.', 'danger')
    
    return render_template('edit_post.html', post=post, categories=categories, tags=tags)

@app.route('/post/<int:post_id>/delete', methods=['POST'])
@login_required
def delete_post(post_id):
    post = Post.query.get_or_404(post_id)
    if post.author != current_user:
        abort(403)
    
    if post.image_file:
        try:
            os.remove(os.path.join(app.config['UPLOAD_FOLDER'], 'images', post.image_file))
        except:
            pass
    
    if post.audio_file:
        try:
            os.remove(os.path.join(app.config['UPLOAD_FOLDER'], 'audio', post.audio_file))
        except:
            pass
    
    db.session.delete(post)
    try:
        db.session.commit()
        flash('Yazınız silindi!', 'success')
    except:
        db.session.rollback()
        flash('Bir hata oluştu.', 'danger')
    
    return redirect(url_for('home'))

@app.route('/post/<int:post_id>/comment', methods=['POST'])
@login_required
def add_comment(post_id):
    post = Post.query.get_or_404(post_id)
    comment = Comment(
        content=request.form['content'],
        author=current_user,
        post=post
    )
    db.session.add(comment)
    try:
        db.session.commit()
        flash('Yorumunuz eklendi!', 'success')
    except:
        db.session.rollback()
        flash('Bir hata oluştu.', 'danger')
    return redirect(url_for('post', post_id=post.id))

@app.route('/comment/<int:comment_id>/delete', methods=['POST'])
@login_required
def delete_comment(comment_id):
    comment = Comment.query.get_or_404(comment_id)
    if comment.author != current_user:
        abort(403)
    
    db.session.delete(comment)
    try:
        db.session.commit()
        flash('Yorumunuz silindi!', 'success')
    except:
        db.session.rollback()
        flash('Bir hata oluştu.', 'danger')
    
    return redirect(url_for('post', post_id=comment.post_id))

@app.route('/category/<int:category_id>')
def category_posts(category_id):
    category = Category.query.get_or_404(category_id)
    page = request.args.get('page', 1, type=int)
    posts = Post.query.filter_by(category=category).order_by(Post.date_posted.desc()).paginate(page=page, per_page=5)
    return render_template('category_posts.html', category=category, posts=posts)

@app.route('/tag/<int:tag_id>')
def tag_posts(tag_id):
    tag = Tag.query.get_or_404(tag_id)
    page = request.args.get('page', 1, type=int)
    posts = tag.posts.order_by(Post.date_posted.desc()).paginate(page=page, per_page=5)
    return render_template('tag_posts.html', tag=tag, posts=posts)

@app.route('/uploads/images/<filename>')
def uploaded_image(filename):
    return send_from_directory(os.path.join(app.config['UPLOAD_FOLDER'], 'images'), filename)

@app.route('/uploads/audio/<filename>')
def uploaded_audio(filename):
    return send_from_directory(os.path.join(app.config['UPLOAD_FOLDER'], 'audio'), filename)

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True) 