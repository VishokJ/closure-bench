`timescale 1ns / 1ps
module tb;
  logic        clk = 1'b0;
  logic        rst = 1'b0;
  logic        rxd = 1'b1;
  logic        m_axis_tready = 1'b1;
  logic [15:0] prescale = 16'd5;
  wire  [7:0]  m_axis_tdata;
  wire         m_axis_tvalid;
  wire         busy, overrun_error, frame_error;

  always #4 clk = ~clk;

  uart_rx dut (
    .clk(clk), .rst(rst),
    .m_axis_tdata(m_axis_tdata), .m_axis_tvalid(m_axis_tvalid),
    .m_axis_tready(m_axis_tready),
    .rxd(rxd),
    .busy(busy), .overrun_error(overrun_error), .frame_error(frame_error),
    .prescale(prescale)
  );

  bit saw_overrun = 0, saw_frame = 0;
  always @(posedge clk) begin
    if (overrun_error) saw_overrun = 1;
    if (frame_error)   saw_frame = 1;
  end

  task automatic wait_clks(input int n);
    repeat (n) @(negedge clk);
  endtask

  // start + 8 data bits, then drive the stop level and return immediately
  task automatic send_frame_no_stop_wait(input byte unsigned b);
    int bit_clks = int'(prescale) * 8;
    rxd = 1'b0; wait_clks(bit_clks);
    for (int i = 0; i < 8; i++) begin
      rxd = b[i]; wait_clks(bit_clks);
    end
    rxd = 1'b1;
  endtask

  initial begin
    @(negedge clk);
    rst = 1'b1; wait_clks(3);
    rst = 1'b0; wait_clks(3);

    m_axis_tready = 1'b0;
    send_frame_no_stop_wait(8'hA5);

    begin
      int guard = 0;
      while (!m_axis_tvalid) begin
        @(negedge clk);
        guard++;
        if (guard > 200) $fatal(1, "tvalid never rose");
      end
    end
    if (m_axis_tdata !== 8'hA5) $fatal(1, "wrong data 0x%02h", m_axis_tdata);

    // stall for 8 cycles, checking the output is held
    repeat (8) begin
      @(negedge clk);
      if (m_axis_tvalid !== 1'b1) $fatal(1, "tvalid dropped while tready low");
      if (m_axis_tdata !== 8'hA5) $fatal(1, "tdata changed while stalled: 0x%02h", m_axis_tdata);
    end

    m_axis_tready = 1'b1;
    @(negedge clk);
    if (m_axis_tvalid !== 1'b0) $fatal(1, "word not accepted when tready rose");

    wait_clks(100);
    if (saw_overrun) $fatal(1, "unexpected overrun_error");
    if (saw_frame)   $fatal(1, "unexpected frame_error");
    if (m_axis_tvalid) $fatal(1, "spurious extra word");
    $display("PASS");
    $finish;
  end

  initial begin
    #1ms;
    $fatal(1, "timeout");
  end
endmodule
