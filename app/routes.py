import os
from operator import or_, and_

from flask import render_template, redirect, url_for, flash, request, jsonify

from werkzeug.utils import secure_filename

from app.models import Activities, ActivityParticipation, Client, ChatRecords, \
    Evaluations, FriendRelationships, GroupRecords, GroupMembers, Hobby, Tags, ActivityTag, Group  # 修改导入语句
from app.forms import LoginForm, RegistrationForm, ActivityForm, ProfileForm
from flask_login import current_user, login_user, logout_user, login_required

from flask_socketio import emit
from flask_socketio import join_room
import sqlalchemy as sa
import pytz
from datetime import datetime


def to_local_time(utc_time, timezone='Asia/Shanghai'):
    local_tz = pytz.timezone(timezone)
    if utc_time.tzinfo is None:
        utc_time = pytz.UTC.localize(utc_time)
    local_time = utc_time.astimezone(local_tz)
    return local_time


def New():
    new = 0
    # 检查用户是否已登录
    if current_user.is_authenticated:
        new_friend = FriendRelationships.query.filter_by(user_id2=current_user.c_id).all()
        for i in new_friend:
            if i.relationship_status == '0':
                new = new + 1
    return new


def init_routes(app, db, socketio):
    @app.route('/login', methods=['GET', 'POST'])
    def login():
        if current_user.is_authenticated:
            return redirect(url_for('index'))
        form = LoginForm()
        if form.validate_on_submit():
            user = Client.query.filter_by(c_usename=form.c_usename.data).first()
            if user and user.c_password == form.password.data:
                login_user(user, remember=form.remember_me.data)
                activity_zero = Activities.query.filter_by(a_id='0').first()
                if not activity_zero:
                    # 若没有则创建一个
                    new_activity = Activities(
                        a_id='0',
                        a_name='0',
                        event_time=datetime.now(),
                        end_time=datetime.now()
                    )
                    db.session.add(new_activity)
                    db.session.commit()
                return redirect(url_for('index'))
            flash('用户名或密码不存在')
        return render_template('login.html', title='Sign In', form=form)

    @app.route('/register', methods=['GET', 'POST'])
    def register():
        count = Client.query.count() + 1
        timestamp = datetime.now().strftime("%M%S")
        count = str(count) + timestamp
        if current_user.is_authenticated:
            return redirect(url_for('index'))
        form = RegistrationForm()
        if form.validate_on_submit():
            existing_user = Client.query.filter_by(email=form.email.data).first()
            if existing_user:
                flash('该邮箱已被注册，请使用其他邮箱。', 'error')
            else:
                existing_user = Client.query.filter_by(c_usename=form.c_usename.data).first()
                if existing_user:
                    flash('该用户名已被使用，请选择其他用户名。', 'error')
                else:
                    URL = None
                    if form.c_avatar.data:
                        if isinstance(form.c_avatar.data, str):
                            # 如果是字符串，可能需要重新处理
                            flash('头像文件上传失败，请重新选择。', 'error')
                            return render_template('register.html', title='Register', form=form)
                        file = form.c_avatar.data
                        print(file)
                        filename = secure_filename(file.filename)
                        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
                        filename = f"{timestamp}_{filename}"
                        # 确保上传目录存在

                        upload_folder = os.path.join(app.static_folder, 'avatar_dir')
                        if not os.path.exists(upload_folder):
                            os.makedirs(upload_folder)
                        file.save(os.path.join(upload_folder, filename))
                        print("头像保存成功")
                        URL = os.path.join('/static', 'avatar_dir', filename)
                    user = Client(
                        c_id=count,
                        c_usename=form.c_usename.data,
                        email=form.email.data,
                        c_password=form.password.data,
                        c_phonenumber=form.phonenumber.data,
                        c_avatar_URL=URL
                    )
                    db.session.add(user)
                    db.session.commit()
                    flash('注册成功！', 'success')
                    return redirect(url_for('login'))
        return render_template('register.html', title='Register', form=form)

    @app.route('/activity/<int:a_id>/images')
    def get_activity_images(a_id):
        activity = Activities.query.get_or_404(a_id)
        # 构建活动图片文件夹路径
        upload_folder = os.path.join(app.static_folder, 'a_images', activity.a_name)
        image_files = []
        if os.path.exists(upload_folder):
            # 遍历文件夹，获取所有图片文件
            for file in os.listdir(upload_folder):
                if file.lower().endswith(('.png', '.jpg', '.jpeg', '.gif')):
                    image_path = os.path.join('/static', 'a_images', activity.a_name, file)
                    image_files.append(image_path)
        return {'images': image_files}

    @app.route('/logout')
    @login_required
    def logout():
        logout_user()
        return redirect(url_for('index'))

    @app.route('/')
    @app.route('/index', methods=['GET', 'POST'])
    def index():
        sort = request.args.get('sort', 'created_at')
        search = request.args.get('search', '')
        query = Activities.query  # 修改查询对象
        new = New()
        tag_activities = []
        # 搜索排序
        if search:
            tag = Tags.query.filter(Tags.tag_name.contains(search)).first()
            if tag:
                activity_tags = ActivityTag.query.filter_by(tag_id=tag.tag_id)
                for tag in activity_tags:
                    tag_activities.append(tag.a_id)
                if tag_activities:
                    query = query.filter(Activities.a_id.in_(tag_activities))
            else:
                query = query.filter(Activities.a_name.contains(search) | Activities.a_text.contains(search))
        if sort == 'event_time':
            activities = query.order_by(Activities.event_time.asc()).all()
        else:
            activities = query.order_by(Activities.created_at.desc()).all()

        #找到活动评分
        for i in activities:
            comments = (Evaluations.query.filter_by(a_id=i.a_id).order_by(Evaluations.e_time.asc())).all()
            # 计算活动评分均分
            total_rating = 0
            if comments:
                for comment in comments:
                    total_rating += int(comment.rating)
                average_rating = total_rating / len(comments)
                average_rating = str(average_rating)
                average_rating = average_rating[:3]
            else:
                average_rating = 0
            i.total_rating = average_rating
            i.comments_number = len(comments)
            i.participations_number = len(ActivityParticipation.query.filter_by(a_id=i.a_id).all())

        # 寻找活动对应标签
        tags = Tags.query.all()
        activity_tags = ActivityTag.query.all()

        recent_chats = []
        if current_user.is_authenticated:
            # 子查询：获取每个对话的最新消息时间
            subquery = db.session.query(
                ChatRecords.conversation_id,
                sa.func.max(ChatRecords.send_time).label('max_timestamp')
            ).filter(
                ChatRecords.message_id.isnot(None) &
                ((ChatRecords.sender_c_id == current_user.c_id) | (ChatRecords.receiver_c_id == current_user.c_id))
            ).group_by(ChatRecords.conversation_id).subquery()

            # 主查询：获取最新消息的详细信息
            recent_chats_query = db.session.query(ChatRecords, Activities).join(
                subquery,
                (ChatRecords.conversation_id == subquery.c.conversation_id) &
                (ChatRecords.send_time == subquery.c.max_timestamp)
            ).join(
                Activities,
                ChatRecords.activity_id == Activities.a_id
            ).order_by(
                subquery.c.max_timestamp.desc()
            ).limit(5)

            recent_chats = []
            for chat_record, activity in recent_chats_query.all():
                other_user_id = chat_record.receiver_c_id if chat_record.sender_c_id == current_user.c_id else chat_record.sender_c_id
                other_user = Client.query.get(other_user_id)
                local_timestamp = to_local_time(chat_record.send_time)
                recent_chats.append({
                    'conversation_id': chat_record.conversation_id,
                    'activity': activity,
                    'other_user': other_user,
                    'last_message': chat_record,
                    'local_timestamp': local_timestamp
                })
            print("最近聊天:", [(chat['activity'].a_name, chat['other_user'].c_usename,
                                 chat['local_timestamp'].strftime('%Y-%m-%d %H:%M')) for chat in recent_chats])

            # 获取每个活动的前三张图片
            for activity in activities:
                upload_folder = os.path.join(app.static_folder, 'a_images', activity.a_name)
                image_files = []
                if os.path.exists(upload_folder):
                    for file in os.listdir(upload_folder):
                        if file.lower().endswith(('.png', '.jpg', '.jpeg', '.gif')):
                            image_path = os.path.join('/static', 'a_images', activity.a_name, file)
                            image_files.append(image_path)
                            if len(image_files) >= 3:
                                break
                activity.images = image_files

        return render_template('index.html', title='Activity Square', activities=activities,
                               search=search, sort=sort, recent_chats=recent_chats, current_user=current_user, new=new,
                               tags=tags, activity_tags=activity_tags, tag_activities=tag_activities)

    def allowed_file(filename):
        return '.' in filename and filename.rsplit('.', 1)[1].lower() in {'png', 'jpg', 'jpeg', 'gif'}

    @app.route('/activity/create', methods=['GET', 'POST'])
    @login_required
    def activity_create():
        tags = Tags.query.all()
        new = New()
        form = ActivityForm()
        count = Activities.query.count() + 1
        timestamp = datetime.now().strftime("%M%S")
        count = str(count) + timestamp
        URL = None

        if form.validate_on_submit():
            if form.end_time.data <= form.event_time.data:
                flash('结束时间必须晚于开始时间。', 'error')
                return render_template('activity_create.html', title='Create Activity', form=form, new=new, tags=tags)
            activity = Activities(
                a_id=count,
                a_name=form.title.data,
                a_text=form.description.data,
                creator_c_id=current_user.c_id,
                event_time=form.event_time.data,
                end_time=form.end_time.data,
                a_location=form.location.data,
                limit_p=form.max_participants.data,
            )
            db.session.add(activity)
            db.session.commit()
            # 处理图片上传
            if 'images' in request.files:
                files = request.files.getlist('images')
                for file in files:
                    if file and allowed_file(file.filename):
                        filename = secure_filename(file.filename)
                        # 为每个活动创建一个单独的文件夹
                        upload_folder = os.path.join(app.static_folder, 'a_images', count)
                        if not os.path.exists(upload_folder):
                            os.makedirs(upload_folder)
                        file.save(os.path.join(upload_folder, filename))
                print("活动图片保存成功")
            # 标签选择

            selected_tags = request.form.getlist('selected_tags')
            # print(selected_tags)

            # 插入新的标签
            for tag_id in selected_tags:
                new_hobby = ActivityTag(a_id=count, tag_id=tag_id)
                db.session.add(new_hobby)
            db.session.commit()
            # cusename = Client.query.filter(Client.c_id == activity.creator_c_id).first()
            # socketio.emit('new_activity', {
            #     'id': activity.a_id,
            #     'title': activity.a_name,
            #     'creator': cusename,
            #     'event_time': to_local_time(activity.event_time).strftime('%Y-%m-%d %H:%M'),
            #     'end_time': to_local_time(activity.end_time).strftime('%Y-%m-%d %H:%M') if activity.end_time else None
            # })
            flash('活动创建成功！可以在此查看和完善活动标签', 'success')
            return redirect(url_for('activity_manage'))
        return render_template('activity_create.html', title='Create Activity', form=form, new=new, tags=tags)

    @app.route('/activity/<int:a_id>')
    def activity_detail(a_id):
        new = New()
        activity = Activities.query.get_or_404(a_id)
        participations = ActivityParticipation.query.filter_by(a_id=a_id).all()
        # 寻找活动对应标签
        tags = Tags.query.all()
        activity_tags = ActivityTag.query.all()
        comments = (Evaluations.query.filter_by(a_id=a_id).order_by(Evaluations.e_time.asc())).all()

        # 计算活动评分均分
        total_rating = 0
        if comments:
            for comment in comments:
                total_rating += int(comment.rating)
            average_rating = total_rating / len(comments)
            average_rating = str(average_rating)
            average_rating = average_rating[:3]
        else:
            average_rating = 0

        participant_user = ActivityParticipation.query.filter_by(a_id=a_id).all()
        participant_user_id = []
        for user in participations:
            participant_user_id.append(user.participant_c_id)
        
        #活动图片        
        # 动态获取图片列表
        image_dir = os.path.join(app.static_folder, 'a_images', str(a_id))
        if os.path.exists(image_dir):
            # 获取所有图片文件（支持 jpg/png/webp）
            image_files = [f for f in os.listdir(image_dir) 
                        if f.lower().endswith(('.png', '.jpg', '.jpeg', '.webp'))]
        else:
            image_files = []
        return render_template('activity_detail.html', title=activity.a_name, activity=activity,
                               participations=participations, new=new, tags=tags, activity_tags=activity_tags,
                               comments=comments, participant_user_id=participant_user_id,
                               current_user=current_user, average_rating=average_rating, activity_images=image_files)

    @app.route('/activity/<int:a_id>/add_comment', methods=['POST'])
    @login_required
    def add_comment(a_id):
        new = New()
        activity = Activities.query.get_or_404(a_id)
        # 获取表单数据
        evaluation_content = request.form.get('comment-content')
        rating = request.form.get('rating')
        print(evaluation_content)
        # 生成评价ID
        count = Evaluations.query.count() + 1
        timestamp = datetime.now().strftime("%M%S")
        e_id = str(count) + timestamp

        # 创建新的评价记录
        new_comment = Evaluations(
            e_id=e_id,
            user_id=current_user.c_id,
            a_id=a_id,
            evaluation_content=evaluation_content,
            rating=rating,
        )

        # 将评价记录添加到数据库
        db.session.add(new_comment)
        db.session.commit()

        flash('评价提交成功！', 'success')
        return redirect(url_for('activity_detail', a_id=a_id))

    @app.route('/activity/<int:a_id>/join')
    @login_required
    def activity_join(a_id):
        activity = Activities.query.get_or_404(a_id)
        participant_count = ActivityParticipation.query.filter_by(a_id=a_id).count()
        if ActivityParticipation.query.filter_by(participant_c_id=current_user.c_id, a_id=a_id).first():
            flash('你已经参加过这个活动了')
        elif activity.limit_p and participant_count >= activity.limit_p:
            flash('这里已经满员了')
        else:
            participation = ActivityParticipation(participant_c_id=current_user.c_id, a_id=a_id)
            db.session.add(participation)
            db.session.commit()
            flash('参与活动成功！')
        return redirect(url_for('activity_detail', a_id=a_id))

    @app.route('/activity/manage')
    @login_required
    def activity_manage():
        new = New()
        created_activities = Activities.query.filter_by(creator_c_id=current_user.c_id).all()  # 修改为 Activities
        joined_activities = [p.a_id for p in
                             ActivityParticipation.query.filter_by(participant_c_id=current_user.c_id).all()]
        i = ""
        joined = [k for k in Activities.query.filter(Activities.a_id.in_(joined_activities)).all()]
        return render_template('activity_manage.html', title='Manage Activities',
                               created_activities=created_activities, joined_activities=joined, new=new,
                               now=datetime.now())

    @app.route('/activity/edit/<int:activity_id>', methods=['GET', 'POST'])
    @login_required
    def activity_edit(activity_id):
        new = New()
        tags = Tags.query.all()
        activity = Activities.query.get_or_404(activity_id)  # 修改为 Activities
        activity_tag = ActivityTag.query.filter_by(a_id=activity.a_id)
        activity_tags = []
        for h in activity_tag:
            activity_tags.append(h.tag_id)
        # print(activity_tags)
        if activity.creator_c_id != current_user.c_id:
            flash('您无权编辑此活动。', 'error')
            return redirect(url_for('activity_manage'))
        form = ActivityForm()
        if form.validate_on_submit():
            activity.a_name = form.title.data
            activity.a_text = form.description.data
            activity.event_time = form.event_time.data
            activity.end_time = form.end_time.data
            activity.a_location = form.location.data
            activity.limit_p = form.max_participants.data

            # 处理图片上传
            if 'images' in request.files:
                files = request.files.getlist('images')
                for file in files:
                    if file and allowed_file(file.filename):
                        filename = secure_filename(file.filename)
                        # 为每个活动创建一个单独的文件夹
                        upload_folder = os.path.join(app.static_folder, 'a_images', activity.a_id)
                        if not os.path.exists(upload_folder):
                            os.makedirs(upload_folder)
                        file.save(os.path.join(upload_folder, filename))
                        print("活动图片保存成功")

            
            db.session.commit()

            # 标签选择

            selected_tags = request.form.getlist('selected_tags')
            print(selected_tags)
            # 删除当前用户不在新 selected_tags 列表中的爱好记录
            existing_tags = ActivityTag.query.filter_by(a_id=activity.a_id).all()
            for tag in existing_tags:
                if tag.tag_id not in selected_tags:
                    db.session.delete(tag)
                    print("删除成功")

            # 插入新的爱好记录
            for tag_id in selected_tags:
                existing_tags = ActivityTag.query.filter_by(a_id=activity.a_id, tag_id=tag_id).first()
                if not existing_tags:
                    new_tag = ActivityTag(a_id=activity.a_id, tag_id=tag_id)
                    db.session.add(new_tag)
            db.session.commit()
            flash('活动已更新！', 'success')
            return redirect(url_for('activity_manage'))
        elif request.method == 'GET':
            form.title.data = activity.a_name
            form.description.data = activity.a_text
            form.event_time.data = activity.event_time
            form.end_time.data = activity.end_time
            form.location.data = activity.a_location
            form.max_participants.data = activity.limit_p
        return render_template('activity_edit.html', form=form, activity=activity, new=new, tags=tags,
                               activity_tags=activity_tags)

    @app.route('/activity/delete/<int:activity_id>', methods=['POST'])
    @login_required
    def activity_delete(activity_id):
        activity = Activities.query.get_or_404(activity_id)  # 修改为 Activities

        if activity.creator_c_id != current_user.c_id:
            flash('您无权删除此活动。', 'error')
            return redirect(url_for('activity_manage'))
        try:
            ActivityParticipation.query.filter_by(a_id=activity_id).delete()
            Evaluations.query.filter_by(a_id=activity_id).delete()
            ChatRecords.query.filter_by(activity_id=activity_id).delete()
            ActivityTag.query.filter_by(a_id=activity_id).delete()

            db.session.delete(activity)
            db.session.commit()
            socketio.emit('delete_activity', {'id': activity_id})
            flash('活动已删除！', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'删除活动时出错: {str(e)}', 'error')
        return redirect(url_for('activity_manage'))

    @app.route('/activity/leave/<int:activity_id>', methods=['POST'])
    @login_required
    def activity_leave(activity_id):
        activity = Activities.query.get_or_404(activity_id)
        participation = ActivityParticipation.query.filter_by(participant_c_id=current_user.c_id,
                                                              a_id=activity_id).first()
        if not participation:
            flash('您未参与此活动。', 'error')
            return redirect(url_for('activity_manage'))
        db.session.delete(participation)
        db.session.commit()
        flash('您已退出该活动。', 'success')
        return redirect(url_for('activity_manage'))

    @app.route('/friend_chat/<other_id>')
    @login_required
    def friend_chat(other_id):
        other_id = str(other_id)
        new = New()
        chat_records = (ChatRecords.query.filter(or_(
            and_(
                ChatRecords.sender_c_id == current_user.c_id,
                ChatRecords.receiver_c_id == other_id
            ),
            and_(
                ChatRecords.sender_c_id == other_id,
                ChatRecords.receiver_c_id == current_user.c_id
            )
        ))).order_by(ChatRecords.send_time.asc()).all()

        other_user = Client.query.filter_by(c_id=other_id).first()
        conversation_id = "0-" + current_user.c_id + '-' + other_id
        if not other_user:
            flash('用户不存在。', 'error')
            return redirect(url_for('index'))
        # 为消息添加本地时间（如果有消息）
        for chat_record in chat_records:
            chat_record.local_timestamp = to_local_time(chat_record.send_time)
        return render_template('chat.html', title=f'Chat - {other_user.c_usename}', messages=chat_records,
                               other_user=other_user, new=new, conversation_id=conversation_id)

    @app.route('/chat/<conversation_id>')
    @login_required
    def chat(conversation_id):
        new = New()

        print(conversation_id)
        # activity_id, user1_id, user2_id = map(int, conversation_id.split('-'))
        # 从 conversation_id 解析 activity_id 和 user_ids
        try:
            activity_id, user1_id, user2_id = map(str, conversation_id.split('-'))
        except ValueError:
            flash('无效的会话 ID。', 'error')
            return redirect(url_for('index'))

        print("activity_id", activity_id)
        # 获取对方用户信息

        other_user_id = user1_id if current_user.c_id == user2_id else user2_id
        other_user = Client.query.filter_by(c_id=other_user_id).first()
        # 查询消息记录

        if activity_id == '0':
            chat_records = (ChatRecords.query.filter(or_
                                                     (ChatRecords.conversation_id == "0-" + user1_id + "-" + user2_id,
                                                      ChatRecords.conversation_id == "0-" + user2_id + "-" + user1_id))
                            .order_by(ChatRecords.send_time.asc())).all()
            return redirect(url_for('friend_chat', other_id=other_user_id))
        else:
            chat_records = ChatRecords.query.filter(or_(ChatRecords.conversation_id == activity_id + '-' + user1_id + '-' + user2_id,
                                                        ChatRecords.conversation_id == activity_id + '-' + user2_id + '-' + user1_id)).order_by(
                ChatRecords.send_time.asc()).all()
        print(user1_id, user2_id, current_user.c_id)
        # 验证当前用户是否是会话的参与者
        if current_user.c_id not in (user1_id, user2_id):
            flash('您无权访问此会话。', 'error')
            return redirect(url_for('index'))

        # 获取活动信息
        activity = Activities.query.get(activity_id)  # 修改为 Activities
        if not activity:
            flash('活动不存在。', 'error')
            return redirect(url_for('index'))

        # print("other:",user1_id,user2_id,current_user.c_id)

        if not other_user:
            flash('用户不存在。', 'error')
            return redirect(url_for('index'))

        # 为消息添加本地时间（如果有消息）
        for chat_record in chat_records:
            chat_record.local_timestamp = to_local_time(chat_record.send_time)
        # 即使 messages 为空，也允许进入聊天页面
        return render_template('chat.html', title=f'Chat - {activity.a_name} - {other_user.c_usename}',
                               activity=activity, messages=chat_records, conversation_id=conversation_id,
                               other_user=other_user, new=new,current_user=current_user)

    @socketio.on('send_message')
    def handle_send_message(data):
        print(data)
        if 'activity_id' in data:
            activity_id = data['activity_id']
            activity = Activities.query.get(activity_id)  # 修改为 Activities
        content = data['content']
        receiver_id = data['receiver_id']

        count = ChatRecords.query.count() + 1
        timestamp = datetime.now().strftime("%M%S")
        count = str(count) + timestamp
        if content:
            user_ids = [int(current_user.c_id), int(receiver_id)]
            print(user_ids)
            if 'activity_id' in data:
                conversation_id = f"{activity_id}-{user_ids[0]}-{user_ids[1]}"
                activity = Activities.query.get(data['activity_id'])
                chat_record = ChatRecords(
                    message_id=count,
                    sender_c_id=current_user.c_id,
                    receiver_c_id=receiver_id,
                    activity_id=activity_id,
                    conversation_id=conversation_id,
                    message_content=content
                )
            else:
                conversation_id = f"0-{user_ids[0]}-{user_ids[1]}"
                chat_record = ChatRecords(
                    message_id=count,
                    sender_c_id=current_user.c_id,
                    receiver_c_id=receiver_id,
                    activity_id=0,
                    conversation_id=conversation_id,
                    message_content=content
                )

            db.session.add(chat_record)
            db.session.commit()
            print(f"消息已保存在对话编号 {conversation_id}，消息为: {content}")
            emit('new_message', {'sender': current_user.c_usename, 'content': content,
                                 'sender_avatar':current_user.c_avatar_URL}, room=conversation_id)
            receiver = Client.query.get(receiver_id)
            local_timestamp = to_local_time(chat_record.send_time)
            if 'activity_id' in data:  # 发送到index.html中的最近消息
                socketio.emit('new_chat_message', {
                    'conversation_id': conversation_id,
                    'activity_id': activity_id,
                    'activity_title': activity.a_name,
                    'other_user': receiver.c_usename,
                    'timestamp': local_timestamp.strftime('%Y-%m-%d %H:%M'),

                })
            else:
                socketio.emit('new_chat_message', {
                    'conversation_id': conversation_id,
                    'activity_id': 0,
                    'activity_title': '',
                    'other_user': receiver.c_usename,
                    'timestamp': local_timestamp.strftime('%Y-%m-%d %H:%M'),

                })
        else:
            print(f"not found")

    @socketio.on('join')
    def handle_join(data):
        room = str(data['room'])
        join_room(room)
        print(f"用户加入对话编号 {room}")

    @app.route('/relationship', methods=['POST', 'GET'])
    @login_required
    def relationship():
        new = New()
        f_search = request.args.get('f_search', '')

        relationships = (FriendRelationships.query.filter(
            or_(
                FriendRelationships.user_id1 == current_user.c_id,
                FriendRelationships.user_id2 == current_user.c_id
            )
        )).order_by(FriendRelationships.user_id1.desc()).all()
        others = set()
        m_others = set()
        a_others = set()
        for relationship in relationships:
            # 好友Client表
            if relationship.relationship_status == '1':
                other = relationship.friend1 if relationship.user_id2 == current_user.c_id else relationship.friend2
                others.add(other)
            elif relationship.relationship_status == '0':
                other = relationship.friend1 if relationship.user_id2 == current_user.c_id else relationship.friend2
                m_others.add(other)
            else:
                other = relationship.friend1 if relationship.user_id2 == current_user.c_id else relationship.friend2
                a_others.add(other)

        if f_search:
            query = Client.query.filter(Client.c_usename.contains(f_search))  # 搜索Client表
            others = set()
            m_others = set()
            n_others = set()  # 确保唯一性
            a_others = set()

            for i in query.all():
                other_id = i.c_id
                re = FriendRelationships.query.filter(
                    ((FriendRelationships.user_id1 == other_id) & (FriendRelationships.user_id2 == current_user.c_id)) |
                    ((FriendRelationships.user_id1 == current_user.c_id) & (FriendRelationships.user_id2 == other_id))
                ).first()
                if re:
                    if re.relationship_status == '1':
                        others.add(i)  # 将好友添加到集合中
                    elif re.relationship_status == '0':
                        m_others.add(i)  # 将待处理关系的用户添加到集合中
                    elif re.relationship_status == '2':
                        a_others.add(i)
                else:
                    n_others.add(i)  # 将没有关系的用户添加到集合中

            states = 1
            return render_template("relationship.html", others=list(others), f_search=f_search,
                                   current_user=current_user, relationships=relationships, m_others=list(m_others),
                                   n_others=list(n_others), states=states, new=new, a_others=list(a_others))

        states = 0
        return render_template("relationship.html", others=list(others), f_search=f_search,
                               current_user=current_user, relationships=relationships, states=states,
                               m_others=list(m_others), new=new, a_others=list(a_others))

    @app.route('/delete_friend', methods=['POST'])
    def delete_friend():
        friend_id = request.form.get('delete')
        current_user_id = current_user.c_id

        # 查找好友关系记录并删除
        relationship = FriendRelationships.query.filter(
            ((FriendRelationships.user_id1 == current_user_id) & (FriendRelationships.user_id2 == friend_id)) |
            ((FriendRelationships.user_id1 == friend_id) & (FriendRelationships.user_id2 == current_user_id))
        ).first()

        db.session.delete(relationship)
        db.session.commit()
        flash('好友已删除', 'success')

        return redirect(url_for('relationship'))

    @app.route('/profile', methods=['GET', 'POST'])
    @login_required
    def profile():
        new = New()
        form = ProfileForm(obj=current_user)
        tags = Tags.query.all()
        user_hobby = Hobby.query.filter_by(c_id=current_user.c_id).all()
        hobbies = []
        for h in user_hobby:
            hobbies.append(h.tag_id)
        if request.method == 'GET':
            form.username.data = current_user.c_usename  # 给 username 字段赋值

        if form.validate_on_submit():
            current_user.c_usename = form.username.data  # 用户名保存
            current_user.email = form.email.data  # 邮箱保存
            URL = None
            # 头像保存
            if form.c_avatar.data:
                print(form.c_avatar.data)
                if isinstance(form.c_avatar.data, str):
                    # 如果是字符串，可能需要重新处理
                    flash('头像文件上传失败，请重新选择。', 'error')
                    return render_template('profile.html', new=new, title='Profile', form=form,
                                           current_user=current_user)
                file = form.c_avatar.data
                print(file)
                filename = secure_filename(file.filename)
                timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
                filename = f"{timestamp}_{filename}"
                # 动态生成上传目录
                upload_folder = os.path.join(app.static_folder, 'avatar_dir')
                if not os.path.exists(upload_folder):
                    try:
                        os.makedirs(upload_folder)
                    except OSError as e:
                        flash(f'创建上传目录时出错: {e}', 'error')
                        return render_template('profile.html', new=new, title='Profile', form=form,
                                               current_user=current_user)
                try:
                    file.save(os.path.join(upload_folder, filename))
                    print("头像保存成功")
                    URL = os.path.join('/static', 'avatar_dir', filename)
                except Exception as e:
                    flash(f'保存头像文件时出错: {e}', 'error')
                    return render_template('profile.html', title='Profile', form=form,
                                           current_user=current_user)
            if URL is not None:
                current_user.c_avatar_URL = URL
            db.session.commit()

            # 标签选择

            selected_tags = request.form.getlist('selected_tags')
            print(selected_tags)
            # 删除当前用户不在新 selected_tags 列表中的爱好记录
            existing_hobbies = Hobby.query.filter_by(c_id=current_user.c_id).all()
            for hobby in existing_hobbies:
                if hobby.tag_id not in selected_tags:
                    db.session.delete(hobby)
                    print("删除成功")

            # 插入新的爱好记录
            for tag_id in selected_tags:
                existing_hobby = Hobby.query.filter_by(c_id=current_user.c_id, tag_id=tag_id).first()
                if not existing_hobby:
                    new_hobby = Hobby(c_id=current_user.c_id, tag_id=tag_id)
                    db.session.add(new_hobby)
            db.session.commit()
            flash('更新成功')
            return redirect(url_for('profile'))
        return render_template('profile.html', title='Profile', form=form,
                               current_user=current_user, tags=tags, hobbies=hobbies, new=new)

    @app.route('/delete_account', methods=['POST'])
    @login_required
    def delete_account():
        user = current_user._get_current_object()
        logout_user()
        db.session.delete(user)
        db.session.commit()
        flash('您的账号已成功注销。', 'success')
        return redirect(url_for('index'))

    @app.route('/add_friend_request', methods=['POST'])
    @login_required
    def add_friend_request():
        friend_id = request.form.get('friend_id')
        current_user_id = current_user.c_id

        # 创建新的好友申请记录
        new_friend_request = FriendRelationships(
            user_id1=current_user_id,
            user_id2=friend_id,
            relationship_status='0'
        )

        try:
            # 将新记录添加到数据库
            db.session.add(new_friend_request)
            db.session.commit()
            flash('好友申请已发送！', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'申请好友时出现错误: {str(e)}', 'error')

        return redirect(url_for('relationship'))

    @app.route('/change_friend_request', methods=['POST'])
    @login_required
    def change_friend_request():
        friend_id = request.form.get('friend_id')
        current_user_id = current_user.c_id

        # 查找对应的好友关系记录
        relationship = FriendRelationships.query.filter(
            ((FriendRelationships.user_id1 == current_user_id) & (FriendRelationships.user_id2 == friend_id)) |
            ((FriendRelationships.user_id1 == friend_id) & (FriendRelationships.user_id2 == current_user_id))
        ).first()

        if relationship:
            try:
                # 修改关系状态为 0
                relationship.relationship_status = '0'
                db.session.commit()
                flash('好友申请状态已更新！', 'success')
            except Exception as e:
                db.session.rollback()
                flash(f'更新好友申请状态时出现错误: {str(e)}', 'error')
        else:
            flash('未找到对应的好友关系记录，无法更新状态。', 'error')

        return redirect(url_for('relationship'))

    @app.route('/accept_friend_request', methods=['POST', 'GET'])
    @login_required
    def accept_friend_request():
        new = New()
        relationships = FriendRelationships.query.filter(
            and_(
                FriendRelationships.user_id2 == current_user.c_id,
                FriendRelationships.relationship_status == '0'
            )
        ).all()

        return render_template('accept_friend_request.html', relationships=relationships, new=new)

    @app.route('/friend_request/<friend_id>', methods=['POST', 'GET'])
    @login_required
    def friend_request(friend_id):

        if request.method == 'POST':
            states = request.form.get('states')
            relationship = FriendRelationships.query.filter(
                ((FriendRelationships.user_id2 == current_user.c_id) &
                 (FriendRelationships.user_id1 == friend_id)) |
                ((FriendRelationships.user_id2 == friend_id) &
                 (FriendRelationships.user_id1 == current_user.c_id))

            ).first()

            if relationship:
                if states == '1':
                    relationship.relationship_status = '1'
                else:
                    relationship.relationship_status = '2'
                try:
                    db.session.commit()
                    flash('好友请求状态已更新！', 'success')
                except Exception as e:
                    db.session.rollback()
                    flash(f'更新好友请求状态时出现错误: {str(e)}', 'error')
            else:
                flash('未找到对应的好友关系记录。', 'error')

        relationships = FriendRelationships.query.filter(
            and_(
                FriendRelationships.user_id2 == current_user.c_id,
                FriendRelationships.relationship_status == '0'
            )
        ).all()

        return redirect(url_for('accept_friend_request'))

    @app.route('/group_list', methods=['GET', 'POST'])
    def group_list():

        new = New()
        g_search = request.args.get('g_search', '')
        # 已参与群聊
        group_memberships = GroupMembers.query.filter_by(c_id=current_user.c_id).all()
        groups = [membership.group for membership in group_memberships]
        # 未参与群聊
        all_groups = Group.query.all()
        n_groups = [group for group in all_groups if group not in groups]
        # 统计每个群聊的成员数量
        group_member_counts = {}
        for group in all_groups:
            member_count = GroupMembers.query.filter_by(g_id=group.g_id).count()
            group_member_counts[group.g_id] = member_count
        if g_search:
            query = Group.query.filter(Group.g_name.contains(g_search))  # 搜索Group表
            group_memberships = GroupMembers.query.filter_by(c_id=current_user.c_id).all()
            temp_groups = [membership.group for membership in group_memberships]
            groups = [group for group in temp_groups if group in query]

            n_groups = [group for group in query if group not in groups]
            states = 1
            return render_template("group_list.html", groups=groups, n_groups=n_groups, new=new, states=states,
                                   current_user=current_user,group_member_counts=group_member_counts)
        states = 0
        return render_template('group_list.html', groups=groups, n_groups=n_groups, new=new, states=states,
                               current_user=current_user,group_member_counts=group_member_counts)

    @app.route('/group_chat/create', methods=['GET', 'POST'])
    @login_required
    def group_chat_create():
        new = New()
        if request.method == 'POST':
            count = Group.query.count() + 1
            timestamp = datetime.now().strftime("%M%S")
            count = str(count) + timestamp
            g_id = count
            name = request.form.get('name')
            group_chat = Group(g_id=count, g_name=name, creator_id=current_user.c_id)
            db.session.add(group_chat)
            db.session.commit()
            # 群主自动加入群聊
            count = GroupMembers.query.count() + 1
            count = str(count) + timestamp
            member = GroupMembers(m_id=count, g_id=g_id, c_id=current_user.c_id)
            db.session.add(member)
            db.session.commit()
            flash('群聊创建成功！', 'success')
            return redirect(url_for('group_chat_detail', g_id=count))
        return render_template('group_chat_create.html', new=new)

    @app.route('/group_chat/<g_id>')  # /group_chat/10115
    @login_required
    def group_chat_detail(g_id):
        new = New()
        group_chat = Group.query.get_or_404(g_id)
        temp = [i.c_id for i in GroupMembers.query if i.g_id == g_id]
        member_ids = [Member.c_id for Member in GroupMembers.query.filter(
            and_(
                GroupMembers.g_id == g_id,
                GroupMembers.c_id.isnot(None)
            )
        ).all()]  # group_members类型列表
        members = [member for member in Client.query.filter().all() if member.c_id in member_ids]
        print(FriendRelationships.query.all())
        messages = GroupRecords.query.filter_by(g_id=g_id).order_by(
            GroupRecords.chat_date.asc()).all()
        return render_template('group_chat_detail.html', new=new, group_chat=group_chat,
                               messages=messages, members=members, current_user=current_user)

    @app.route('/group_chat/join/<g_id>', methods=['POST'])
    @login_required
    def group_chat_join(g_id):
        count = GroupMembers.query.count() + 1
        timestamp = datetime.now().strftime("%M%S")
        count = str(count) + timestamp
        existing_member = GroupMembers.query.filter_by(g_id=g_id,
                                                       c_id=current_user.c_id).first()
        if existing_member:
            flash('你已经在该群聊中。', 'error')
        else:
            member = GroupMembers(m_id=count, g_id=g_id, c_id=current_user.c_id)
            db.session.add(member)
            db.session.commit()
            flash('你已加入该群聊。', 'success')
        return redirect(url_for('group_chat_detail', g_id=g_id))

    @app.route('/group_chat_leave/<g_id>', methods=['POST'])
    @login_required
    def group_chat_leave(g_id):
        group_chat = Group.query.get_or_404(g_id)
        existing_member = GroupMembers.query.filter_by(g_id=g_id, c_id=current_user.c_id).first()
        if existing_member:
            db.session.delete(existing_member)
            db.session.commit()
            flash('你已退出该群聊。', 'success')
        else:
            flash('你不在该群聊中，无法退出。', 'error')
        return redirect(url_for('group_list'))

    @socketio.on('send_group_message')
    def handle_send_group_message(data):
        print("data:", data)
        g_id = data['g_id']
        content = data['content']
        count = GroupRecords.query.count() + 1
        timestamp = datetime.now().strftime("%M%S")
        count = str(count) + timestamp
        message = GroupRecords(
            message_id=count,
            g_id=g_id,
            sender_c_id=current_user.c_id,
            chat_content=content
        )
        try:
            db.session.add(message)
            db.session.commit()
            group_chat = Group.query.get(g_id)
            emit('new_group_message', {'sender': current_user.c_usename, 'content': content,
                                       'sender_avatar':current_user.c_avatar_URL}, room=g_id)
        except Exception as e:
            db.session.rollback()
            print(f"数据库操作出错: {e}")

    @socketio.on('join_group_chat')
    def handle_join_group_chat(data):
        group_chat_id = data['group_chat_id']
        join_room(group_chat_id)
        print(f"用户加入群聊编号 {group_chat_id}")

    # 群主踢人
    @app.route('/group_chat/kick/<g_id>/<user_id>', methods=['POST'])
    @login_required
    def group_chat_kick(g_id, user_id):
        group_chat = Group.query.get_or_404(g_id)
        if current_user.c_id != group_chat.creator_id:
            flash('您不是群主，无法踢人。', 'error')
            return redirect(url_for('group_chat_detail', g_id=g_id))

        member_to_kick = GroupMembers.query.filter_by(g_id=g_id, c_id=user_id).first()
        if not member_to_kick:
            flash('用户不在该群聊中。', 'error')
            return redirect(url_for('group_chat_detail', g_id=g_id))

        db.session.delete(member_to_kick)
        db.session.commit()
        flash('用户已被踢出群聊。', 'success')
        return redirect(url_for('group_chat_detail', g_id=g_id))

    @app.route('/group_delete/<g_id>', methods=['POST'])
    @login_required
    def group_delete(g_id):
        group_chat = Group.query.get_or_404(g_id)
        if current_user.c_id != group_chat.creator_id:
            flash('您不是群主，无法解散群聊。', 'error')
            return redirect(url_for('group_chat_detail', g_id=g_id))

        try:
            GroupRecords.query.filter_by(g_id=g_id).delete()
            GroupMembers.query.filter_by(g_id=g_id).delete()
            db.session.delete(group_chat)
            db.session.commit()

            flash('群聊已成功解散！', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'解散群聊时出现错误: {str(e)}', 'error')
        return redirect(url_for('group_list'))

    @app.route('/show_commend', methods=['POST', 'GET'])
    @login_required
    def show_commend():
        new = New()
        commends = Evaluations.query.filter(Evaluations.user_id == current_user.c_id).all()
        print(commends)
        activities = Activities.query.filter(Activities.creator_c_id == current_user.c_id).all()
        adv_rating = 0
        sum_activities = 0
        for activity in activities:
            user_commend = Evaluations.query.filter(Evaluations.a_id == activity.a_id).all()
            temp = 0
            for commend in user_commend:
                temp += commend.rating
            if len(user_commend) != 0:
                temp = temp / len(user_commend)
                adv_rating += temp
                sum_activities += 1
        if sum_activities != 0:
            adv_rating = adv_rating / sum_activities
        else:
            adv_rating = 0
        print(adv_rating)
        return render_template('show_commend.html', commends=commends, new=new, adv_rating=adv_rating)

    @app.route('/add_tag', methods=['GET', 'POST'])
    def add_tag():
        if request.method == 'POST':
            new_tag = request.form.get('new_tag')
            if not new_tag or len(new_tag.strip()) == 0:
                flash('标签名称不能为空', 'error')
                return redirect(url_for('add_tag'))

            if len(new_tag) > 20:
                flash('标签名称不能超过20个字符', 'error')
                return redirect(url_for('add_tag'))

            count = Activities.query.count() + 1
            timestamp = datetime.now().strftime("%M%S")
            tag_id = str(count) + timestamp
            tag_desc = current_user.c_id
            tag = Tags(tag_id=tag_id, tag_name=new_tag, tag_desc=tag_desc)

            try:
                db.session.add(tag)
                db.session.commit()
                flash('标签添加成功!', 'success')
            except Exception as e:
                db.session.rollback()
                flash('添加标签失败: ' + str(e), 'error')

            return redirect(url_for('add_tag'))

        # GET请求返回页面
        return render_template('add_tag.html')

    @app.route('/delete_tag', methods=['POST'])
    def delete_tag():
        try:
            data = request.get_json()
            tag_id = data.get('tag_id')

            if not tag_id:
                return jsonify(success=False, message="缺少标签ID"), 400

            # 示例删除逻辑（替换为你的实际代码）
            tag_to_delete = Tags.query.get(tag_id)
            if not tag_to_delete:
                return jsonify(success=False, message="标签不存在"), 404

            db.session.delete(tag_to_delete)
            db.session.commit()

            return jsonify(success=True)
        except Exception as e:
            db.session.rollback()
            return jsonify(success=False, message=str(e)), 500

    @app.route('/add_activity_tag/<activity_id>', methods=['GET', 'POST'])
    def add_activity_tag(activity_id):
        # 获取来源页面（需要验证）
        referrer = request.referrer

        # 验证逻辑（防止跨站攻击）
        safe_host = request.host_url
        if referrer and referrer.startswith(safe_host):
            back_url = referrer
        else:
            back_url = url_for('index')  # 默认回退页面

        if request.method == 'POST':
            new_tag = request.form.get('new_tag')
            if not new_tag or len(new_tag.strip()) == 0:
                flash('标签名称不能为空', 'error')
                return redirect(url_for('add_activity_tag'))

            if len(new_tag) > 20:
                flash('标签名称不能超过20个字符', 'error')
                return redirect(url_for('add_activity_tag'))

            # 生成tag_id的逻辑
            count = Activities.query.count() + 1
            timestamp = datetime.now().strftime("%M%S")
            tag_id = str(count) + timestamp

            # 从表单获取的是活动ID，直接赋值给a_id
            a_id = activity_id  # 确保前端传递的是a_id字段

            # 创建新标签和关联
            tag = Tags(tag_id=tag_id, tag_name=new_tag)
            activity_tag = ActivityTag(a_id=a_id, tag_id=tag_id)
            try:
                db.session.add(tag)
                db.session.add(activity_tag)
                db.session.commit()
                flash('标签添加成功!', 'success')
            except Exception as e:
                db.session.rollback()
                flash('添加标签失败: ' + str(e), 'error')

            return redirect(back_url)

        # GET请求处理：返回对应的模板
        # 可能需要获取所有活动供页面选择
        activity = Activities.query.get_or_404(activity_id)
        return render_template('add_activity_tag.html', activity=activity)

    @app.route('/delete_activity_tag', methods=['POST'])
    def delete_activity_tag():
        try:
            data = request.get_json()
            tag_id = data.get('tag_id')
            if not tag_id:
                return jsonify(success=False, message="缺少标签ID"), 400

            # 先删除关联表记录
            delete_count = ActivityTag.query.filter_by(tag_id=tag_id).delete()

            # 再删除标签本身
            tag_to_delete = Tags.query.get(tag_id)
            if not tag_to_delete:
                return jsonify(success=False, message="标签不存在"), 404

            db.session.delete(tag_to_delete)

            db.session.commit()

            return jsonify(success=True, deleted_associations=delete_count)
        except Exception as e:
            db.session.rollback()
            return jsonify(success=False, message=f"删除失败: {str(e)}"), 500
